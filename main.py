import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
#import pyvinecopulib as pv
import category_encoders as ce
import math
import seaborn as sns
import requests
import io
import random
import cmath

from scipy.interpolate import interp1d
from time import perf_counter

import pyvinecopulib



"""## load the data"""


start_time = perf_counter()




'''
| Description of fnlwgt (final weight)
|
| The weights on the CPS files are controlled to independent estimates of the
| civilian noninstitutional population of the US

>50K, <=50K.

age: continuous.
workclass: Private, Self-emp-not-inc, Self-emp-inc, Federal-gov, Local-gov, State-gov, Without-pay, Never-worked.
fnlwgt: continuous.
education: Bachelors, Some-college, 11th, HS-grad, Prof-school, Assoc-acdm, Assoc-voc, 9th, 7th-8th, 12th, Masters, 1st-4th, 10th, Doctorate, 5th-6th, Preschool.
education-num: continuous.
marital-status: Married-civ-spouse, Divorced, Never-married, Separated, Widowed, Married-spouse-absent, Married-AF-spouse.
occupation: Tech-support, Craft-repair, Other-service, Sales, Exec-managerial, Prof-specialty, Handlers-cleaners, Machine-op-inspct, Adm-clerical, Farming-fishing, Transport-moving, Priv-house-serv, Protective-serv, Armed-Forces.
relationship: Wife, Own-child, Husband, Not-in-family, Other-relative, Unmarried.
race: White, Asian-Pac-Islander, Amer-Indian-Eskimo, Other, Black.
sex: Female, Male.
capital-gain: continuous.
capital-loss: continuous.
hours-per-week: continuous.
native-country: United-States, Cambodia, England, Puerto-Rico, Canada, Germany, Outlying-US(Guam-USVI-etc), India, Japan, Greece, South, China, Cuba, Iran, Honduras, Philippines, Italy, Poland, Jamaica, Vietnam, Mexico, Portugal, Ireland, France, Dominican-Republic, Laos, Ecuador, Taiwan, Haiti, Columbia, Hungary, Guatemala, Nicaragua, Scotland, Thailand, Yugoslavia, El-Salvador, Trinadad&Tobago, Peru, Hong, Holand-Netherlands.

education-num equivalent to education
'''



req = requests.get("https://archive.ics.uci.edu/ml/machine-learning-databases/adult/adult.data").content
adult = pd.read_csv(io.StringIO(req.decode('utf-8')), header=None, na_values='?', delimiter=r", ")
#adult.dropna()
adult.columns=['age','workclass', 'flnwgt', 'education', 'education-num','marital-status', 'occupation', 'relationship', 'race', 'sex', 'capital-gain',	'capital-loss',	'hours-per-week', 'native-country', 'salary']

 
adult['salary'] = np.select([(adult['salary'] == '>50'), (adult['salary'] == '<=50K')], [ 0, 1 ])

adult.drop(columns= 'flnwgt', inplace=True)
adult.drop(columns= 'education-num', inplace=True)


attr_categorical = ['workclass', 'education', 'marital-status', 'occupation', 'relationship', 'race', 'sex', 'native-country','salary']
attr_woe = 'salary'
epsilon = 1.0

df=adult

"""# preprocess"""
print("preprocess")
encoder = ce.WOEEncoder(cols=attr_categorical)
data = encoder.fit_transform(df, y=df[attr_woe])

decoder_dict = {col:{data[col][i]:df[col][i] for i in data.index} for col in attr_categorical}

"""#Marginals

### Mechanisms
"""

class PrivItem:
	def __init__(self, q, id):
		self.id = id
		self.q = q
		self.error = None

def basic(items, f):
	# print(f'f = {f}')
	for item in items:
		item.error = f * item.q

	maximum = max(map(lambda x: x.error, items))

	for item in items:
		item.error = math.exp(item.error - maximum)

	uniform = sum(map(lambda x: x.error, items)) * random.random()
	# print(f'maximum = {maximum}, uniform = {uniform}')
	for item in items:
		# print(f'new uniform = {uniform}')
		uniform -= item.error
		if uniform <= 0:
			break

	return item


def run_exp_mechanism(items, eps):
	return basic(items, eps / 2)

def EFPA(histogram, epsilon):
	dft_coeffs = np.fft.rfft(histogram)

	# first coefficient is not used
	error_coeffs = [2 * abs(coeff) ** 2 for coeff in dft_coeffs[1:]]

	m = len(dft_coeffs)

	# last coeff has twice the error only if the number of coeffs is odd
	# otherwise it only counts for one times the error.
	if len(histogram) % 2 == 0:
		error_coeffs[-1] /= 2

	priv_items = []
	for k in range(m - 1):
		kept_coeffs = 2 * k + 1
		perturbation_error = np.sqrt(2) * (kept_coeffs) / (epsilon / 2)
		total_error = np.sqrt(sum(error_coeffs[k:])) + perturbation_error
		priv_items.append(PrivItem(-total_error, [k, kept_coeffs]))
		# print(perturbation_error, sqrt(sum(error_coeffs[k:])), total_error)

	# For final term, keep all fourier coefficients
	# Perturbation error includes len(histogram) terms
	# Reconstruction error is zero
	k = m - 1
	kept_coeffs = len(histogram)
	priv_items.append(PrivItem(-np.sqrt(2) * kept_coeffs / (epsilon / 2),
							   [k, kept_coeffs]))
	# print(sqrt(2) * kept_coeffs / (epsilon / 2), 0, sqrt(2) *
	# kept_coeffs / (epsilon / 2))

	picked_item = run_exp_mechanism(priv_items, epsilon / 2)
	lambda_ = np.sqrt(picked_item.id[1]) / (epsilon / 2)
	picked_k = picked_item.id[0] + 1

	# for item in priv_items:
	#     print(item.q, item.id, item.error)
	# print('Picked item:')
	# print(picked_item.q, picked_item.id, picked_item.error)

	for j in range(m):
		if j < picked_k:
			(magnitude, angle) = cmath.polar(dft_coeffs[j])
			dft_coeffs[j] = cmath.rect(magnitude + np.random.laplace(lambda_),
									   angle)
		else:
			dft_coeffs[j] = 0
	# print(dft_coeffs)

	return [x.real for x in np.fft.irfft(dft_coeffs, len(histogram))]


def laplace_mechanism(histogram, epsilon):
	lambda_ = 2 / epsilon  # Sensitivity of histogram query is 2
	noisy_histogram = [count + np.random.laplace(0, lambda_)
					   for count in histogram]

	return noisy_histogram

"""### EDF"""
print("edfs")
def dp_histogram(x):
  
	unq, counts = np.unique(x,return_counts=True)
  dp_hist = EFPA(counts, epsilon)

  dp_hist = [ np.round(n) for n in dp_hist ] 
  
  dp_hist=np.array(dp_hist)

  
  dp_hist[ dp_hist < 0.0] = 0

#do the size shuffle
  r = len(x)/np.sum(dp_hist)
  dp_hist= dp_hist*r
  dp_hist[np.argmax(dp_hist)]+= (len(x)-np.sum(dp_hist))
 

  return unq, dp_hist

dp_hists = {col:dp_histogram(data[col]) for col in data.columns}

dp_edfs = {col: np.cumsum(dp_hists[col][1])/(np.sum(dp_hists[col][1])+1)  for col in data.columns}




pse_obs = []
for col in data.columns:
  f = interp1d(dp_hists[col][0], dp_edfs[col], kind='previous', bounds_error=False, fill_value=(0.0, 1.0))
  pse_obs.append(np.array(f(data[col])))
pse_obs=np.array(pse_obs).T


"""# Gaussian Copula

# Vine Copula
"""
print("vine")
vine_cop = pyvinecopulib.Vinecop(data=pse_obs)

"""# Sampling"""
print("sampling")
sample = pd.DataFrame(np.asarray(vine_cop.simulate(data.shape[0])), columns=data.columns)


for col in data.columns:
  f = interp1d( dp_edfs[col],dp_hists[col][0], kind='next', bounds_error=False, fill_value=(np.min(dp_hists[col][0]), np.max(dp_hists[col][0])))
  sample[col]=np.array(f(sample[col])).T




def FindClosestVal(num, d):
	return d[num] if num in d else d[min(d.keys(), key=lambda k: abs(k-num))]


for col in attr_categorical:
  sample[col] = sample[col].apply(FindClosestVal, d=decoder_dict[col])

"""# Comparison"""
print("comparison")
 

 
 

sample.to_csv(f'adult_eps.csv', index=False)  
stop_time = perf_counter()

print(f"Done in {stop_time - start_time:0.4f} seconds")