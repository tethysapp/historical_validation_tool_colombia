import datetime as dt
import io
import traceback
from csv import writer as csv_writer

import geoglows
import math
import hydrostats as hs
import hydrostats.data as hd
import pandas as pd
import numpy as np

import plotly.graph_objs as go
import requests
import scipy.stats as sp
from HydroErr.HydroErr import metric_names, metric_abbr
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from scipy import integrate
from tethys_sdk.gizmos import PlotlyView
import numpy as np

## global values ##
watershed = 'none'
subbasin = 'none'
comid = 'none'
codEstacion = 'none'
nomEstacion = 'none'
s = None
simulated_df = pd.DataFrame({'A' : []})
observed_df = pd.DataFrame({'A' : []})
corrected_df = pd.DataFrame({'A' : []})
forecast_df =pd.DataFrame({'A' : []})
fixed_stats = None
forecast_record = None
fixed_records = None


def home(request):
	"""
	Controller for the app home page.
	"""

	# List of Metrics to include in context
	metric_loop_list = list(zip(metric_names, metric_abbr))

	context = {
		"metric_loop_list": metric_loop_list
	}

	return render(request, 'historical_validation_tool_colombia/home.html', context)


def get_popup_response(request):
	"""
	Get simulated data from api
	"""
	get_data = request.GET
	return_obj = {}

	global watershed
	global subbasin
	global comid
	global codEstacion
	global nomEstacion
	global s
	global simulated_df
	global observed_df
	global corrected_df
	global forecast_df
	global fixed_stats
	global forecast_record
	global fixed_records

	try:
		#get station attributes
		watershed = get_data['watershed']
		subbasin = get_data['subbasin']
		comid = get_data['streamcomid']
		codEstacion = get_data['stationcode']
		nomEstacion = get_data['stationname']

		# get Simulated Streamflow
		simulated_df = geoglows.streamflow.historic_simulation(comid, forcing='era_5', return_format='csv')
		# Removing Negative Values
		simulated_df[simulated_df < 0] = 0
		simulated_df.index = simulated_df.index.to_series().dt.strftime("%Y-%m-%d")
		simulated_df.index = pd.to_datetime(simulated_df.index)
		simulated_df = pd.DataFrame(data=simulated_df.iloc[:, 0].values, index=simulated_df.index, columns=['Simulated Streamflow'])

		'''Get Observed Data'''
		url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(
			codEstacion)
		s = requests.get(url, verify=False).content
		df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0)
		df.index = pd.to_datetime(df.index)

		datesDischarge = df.index.tolist()
		dataDischarge = df.iloc[:, 0].values
		dataDischarge.tolist()

		if isinstance(dataDischarge[0], str):
			dataDischarge = map(float, dataDischarge)

		observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

		'''Correct the Bias in Sumulation'''

		corrected_df = geoglows.bias.correct_historical(simulated_df, observed_df)

		'''Get Forecasts'''
		forecast_df = geoglows.streamflow.forecast_stats(comid, return_format='csv')
		# Removing Negative Values
		forecast_df[forecast_df < 0] = 0

		'''Correct Bias Forecasts'''
		fixed_stats = geoglows.bias.correct_forecast(forecast_df, simulated_df, observed_df)

		'''Get Forecasts Records'''
		try:
			forecast_record = geoglows.streamflow.forecast_records(comid)
			forecast_record[forecast_record < 0] = 0
			forecast_record = forecast_record.loc[forecast_record.index >= pd.to_datetime(forecast_df.index[0] - dt.timedelta(days=8))]

			'''Correct Bias Forecasts Records'''
			fixed_records = geoglows.bias.correct_forecast(forecast_record, simulated_df, observed_df, use_month=-1)
			fixed_records = fixed_records.loc[fixed_records.index >= pd.to_datetime(forecast_df.index[0] - dt.timedelta(days=8))]
		except:
			print('There is no forecast record')

		print("finished get_popup_response")
		return JsonResponse({})

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected station.'})

def get_hydrographs(request):
	"""
	Get observed data from csv files in Hydroshare
	Get historic simulations from ERA Interim
	"""
	get_data = request.GET
	global codEstacion
	global nomEstacion
	global simulated_df
	global observed_df
	global corrected_df

	try:

		'''Plotting Data'''
		observed_Q = go.Scatter(x=observed_df.index, y=observed_df.iloc[:, 0].values, name='Observed', )
		simulated_Q = go.Scatter(x=simulated_df.index, y=simulated_df.iloc[:, 0].values, name='Simulated', )
		corrected_Q = go.Scatter(x=corrected_df.index, y=corrected_df.iloc[:, 0].values, name='Corrected Simulated', )

		layout = go.Layout(
			title='Observed & Simulated Streamflow at <br> {0} - {1}'.format(codEstacion, nomEstacion),
			xaxis=dict(title='Dates', ), yaxis=dict(title='Discharge (m<sup>3</sup>/s)', autorange=True),
			showlegend=True)

		chart_obj = PlotlyView(go.Figure(data=[observed_Q, simulated_Q, corrected_Q], layout=layout))

		context = {
			'gizmo_object': chart_obj,
		}

		return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected station.'})


def get_dailyAverages(request):
	"""
	Get observed data from csv files in Hydroshare
	Get historic simulations from ERA Interim
	"""
	get_data = request.GET
	global codEstacion
	global nomEstacion
	global simulated_df
	global observed_df
	global corrected_df

	try:

		'''Merge Data'''

		merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

		merged_df2 = hd.merge_data(sim_df=corrected_df, obs_df=observed_df)

		'''Plotting Data'''

		daily_avg = hd.daily_average(merged_df)

		daily_avg2 = hd.daily_average(merged_df2)

		daily_avg_obs_Q = go.Scatter(x=daily_avg.index, y=daily_avg.iloc[:, 1].values, name='Observed', )

		daily_avg_sim_Q = go.Scatter(x=daily_avg.index, y=daily_avg.iloc[:, 0].values, name='Simulated', )

		daily_avg_corr_sim_Q = go.Scatter(x=daily_avg2.index, y=daily_avg2.iloc[:, 0].values,
										  name='Corrected Simulated', )

		layout = go.Layout(
			title='Daily Average Streamflow for <br> {0} - {1}'.format(codEstacion, nomEstacion),
			xaxis=dict(title='Days', ), yaxis=dict(title='Discharge (m<sup>3</sup>/s)', autorange=True),
			showlegend=True)

		chart_obj = PlotlyView(go.Figure(data=[daily_avg_obs_Q, daily_avg_sim_Q, daily_avg_corr_sim_Q], layout=layout))

		context = {
			'gizmo_object': chart_obj,
		}

		return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected station.'})


def get_monthlyAverages(request):
	"""
	Get observed data from csv files in Hydroshare
	Get historic simulations from ERA Interim
	"""
	get_data = request.GET
	global codEstacion
	global nomEstacion
	global simulated_df
	global observed_df
	global corrected_df

	try:

		'''Merge Data'''

		merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

		merged_df2 = hd.merge_data(sim_df=corrected_df, obs_df=observed_df)

		'''Plotting Data'''

		monthly_avg = hd.monthly_average(merged_df)

		monthly_avg2 = hd.monthly_average(merged_df2)

		monthly_avg_obs_Q = go.Scatter(x=monthly_avg.index, y=monthly_avg.iloc[:, 1].values, name='Observed', )

		monthly_avg_sim_Q = go.Scatter(x=monthly_avg.index, y=monthly_avg.iloc[:, 0].values, name='Simulated', )

		monthly_avg_corr_sim_Q = go.Scatter(x=monthly_avg2.index, y=monthly_avg2.iloc[:, 0].values,
											name='Corrected Simulated', )

		layout = go.Layout(
			title='Monthly Average Streamflow for <br> {0} - {1}'.format(codEstacion, nomEstacion),
			xaxis=dict(title='Months', ), yaxis=dict(title='Discharge (m<sup>3</sup>/s)', autorange=True),
			showlegend=True)

		chart_obj = PlotlyView(
			go.Figure(data=[monthly_avg_obs_Q, monthly_avg_sim_Q, monthly_avg_corr_sim_Q], layout=layout))

		context = {
			'gizmo_object': chart_obj,
		}

		return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected station.'})


def get_scatterPlot(request):
	"""
	Get observed data from csv files in Hydroshare
	Get historic simulations from ERA Interim
	"""
	get_data = request.GET
	global codEstacion
	global nomEstacion
	global simulated_df
	global observed_df
	global corrected_df

	try:
		'''Merge Data'''

		merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

		merged_df2 = hd.merge_data(sim_df=corrected_df, obs_df=observed_df)

		'''Plotting Data'''

		scatter_data = go.Scatter(
			x=merged_df.iloc[:, 0].values,
			y=merged_df.iloc[:, 1].values,
			mode='markers',
			name='original',
			marker=dict(color='#ef553b')
		)

		scatter_data2 = go.Scatter(
			x=merged_df2.iloc[:, 0].values,
			y=merged_df2.iloc[:, 1].values,
			mode='markers',
			name='corrected',
			marker=dict(color='#00cc96')
		)

		min_value = min(min(merged_df.iloc[:, 1].values), min(merged_df.iloc[:, 0].values))
		max_value = max(max(merged_df.iloc[:, 1].values), max(merged_df.iloc[:, 0].values))

		min_value2 = min(min(merged_df2.iloc[:, 1].values), min(merged_df2.iloc[:, 0].values))
		max_value2 = max(max(merged_df2.iloc[:, 1].values), max(merged_df2.iloc[:, 0].values))

		line_45 = go.Scatter(
			x=[min_value, max_value],
			y=[min_value, max_value],
			mode='lines',
			name='45deg line',
			line=dict(color='black')
		)

		slope, intercept, r_value, p_value, std_err = sp.linregress(merged_df.iloc[:, 0].values,
																	merged_df.iloc[:, 1].values)

		slope2, intercept2, r_value2, p_value2, std_err2 = sp.linregress(merged_df2.iloc[:, 0].values,
																		 merged_df2.iloc[:, 1].values)

		line_adjusted = go.Scatter(
			x=[min_value, max_value],
			y=[slope * min_value + intercept, slope * max_value + intercept],
			mode='lines',
			name='{0}x + {1} (Original)'.format(str(round(slope, 2)), str(round(intercept, 2))),
			line=dict(color='red')
		)

		line_adjusted2 = go.Scatter(
			x=[min_value, max_value],
			y=[slope2 * min_value + intercept2, slope2 * max_value + intercept2],
			mode='lines',
			name='{0}x + {1} (Corrected)'.format(str(round(slope2, 2)), str(round(intercept2, 2))),
			line=dict(color='green')
		)

		layout = go.Layout(title="Scatter Plot for {0} - {1}".format(codEstacion, nomEstacion),
						   xaxis=dict(title='Simulated', ), yaxis=dict(title='Observed', autorange=True),
						   showlegend=True)

		chart_obj = PlotlyView(
			go.Figure(data=[scatter_data, scatter_data2, line_45, line_adjusted, line_adjusted2], layout=layout))

		context = {
			'gizmo_object': chart_obj,
		}

		return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected station.'})


def get_scatterPlotLogScale(request):
	"""
	Get observed data from csv files in Hydroshare
	Get historic simulations from ERA Interim
	"""
	get_data = request.GET
	global codEstacion
	global nomEstacion
	global simulated_df
	global observed_df
	global corrected_df

	try:
		'''Merge Data'''

		merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

		merged_df2 = hd.merge_data(sim_df=corrected_df, obs_df=observed_df)

		'''Plotting Data'''

		scatter_data = go.Scatter(
			x=merged_df.iloc[:, 0].values,
			y=merged_df.iloc[:, 1].values,
			mode='markers',
			name='original',
			marker=dict(color='#ef553b')
		)

		scatter_data2 = go.Scatter(
			x=merged_df2.iloc[:, 0].values,
			y=merged_df2.iloc[:, 1].values,
			mode='markers',
			name='corrected',
			marker=dict(color='#00cc96')
		)

		min_value = min(min(merged_df.iloc[:, 1].values), min(merged_df.iloc[:, 0].values))
		max_value = max(max(merged_df.iloc[:, 1].values), max(merged_df.iloc[:, 0].values))

		line_45 = go.Scatter(
			x=[min_value, max_value],
			y=[min_value, max_value],
			mode='lines',
			name='45deg line',
			line=dict(color='black')
		)

		layout = go.Layout(title="Scatter Plot for {0} - {1} (Log Scale)".format(codEstacion, nomEstacion),
						   xaxis=dict(title='Simulated', type='log', ), yaxis=dict(title='Observed', type='log',
																				   autorange=True), showlegend=True)

		chart_obj = PlotlyView(go.Figure(data=[scatter_data, scatter_data2, line_45], layout=layout))

		context = {
			'gizmo_object': chart_obj,
		}

		return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected station.'})


def get_volumeAnalysis(request):
	"""
	Get observed data from csv files in Hydroshare
	Get historic simulations from ERA Interim
	"""
	get_data = request.GET
	global codEstacion
	global nomEstacion
	global simulated_df
	global observed_df
	global corrected_df

	try:
		'''Merge Data'''

		merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

		merged_df2 = hd.merge_data(sim_df=corrected_df, obs_df=observed_df)

		'''Plotting Data'''

		sim_array = merged_df.iloc[:, 0].values
		obs_array = merged_df.iloc[:, 1].values
		corr_array = merged_df2.iloc[:, 0].values

		sim_volume_dt = sim_array * 0.0864
		obs_volume_dt = obs_array * 0.0864
		corr_volume_dt = corr_array * 0.0864

		sim_volume_cum = []
		obs_volume_cum = []
		corr_volume_cum = []
		sum_sim = 0
		sum_obs = 0
		sum_corr = 0

		for i in sim_volume_dt:
			sum_sim = sum_sim + i
			sim_volume_cum.append(sum_sim)

		for j in obs_volume_dt:
			sum_obs = sum_obs + j
			obs_volume_cum.append(sum_obs)

		for k in corr_volume_dt:
			sum_corr = sum_corr + k
			corr_volume_cum.append(sum_corr)

		observed_volume = go.Scatter(x=merged_df.index, y=obs_volume_cum, name='Observed', )

		simulated_volume = go.Scatter(x=merged_df.index, y=sim_volume_cum, name='Simulated', )

		corrected_volume = go.Scatter(x=merged_df2.index, y=corr_volume_cum, name='Corrected Simulated', )

		layout = go.Layout(
			title='Observed & Simulated Volume at<br> {0} - {1}'.format(codEstacion, nomEstacion),
			xaxis=dict(title='Dates', ), yaxis=dict(title='Volume (Mm<sup>3</sup>)', autorange=True),
			showlegend=True)

		chart_obj = PlotlyView(go.Figure(data=[observed_volume, simulated_volume, corrected_volume], layout=layout))

		context = {
			'gizmo_object': chart_obj,
		}

		return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected station.'})


def volume_table_ajax(request):
	"""Calculates the volumes of the simulated and observed streamflow"""

	get_data = request.GET
	global simulated_df
	global observed_df
	global corrected_df

	try:

		'''Merge Data'''

		merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

		merged_df2 = hd.merge_data(sim_df=corrected_df, obs_df=observed_df)

		'''Plotting Data'''

		sim_array = merged_df.iloc[:, 0].values
		obs_array = merged_df.iloc[:, 1].values
		corr_array = merged_df2.iloc[:, 0].values

		sim_volume = round((integrate.simps(sim_array)) * 0.0864, 3)
		obs_volume = round((integrate.simps(obs_array)) * 0.0864, 3)
		corr_volume = round((integrate.simps(corr_array)) * 0.0864, 3)

		resp = {
			"sim_volume": sim_volume,
			"obs_volume": obs_volume,
			"corr_volume": corr_volume,
		}

		return JsonResponse(resp)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected station.'})


def make_table_ajax(request):
	get_data = request.GET
	global simulated_df
	global observed_df
	global corrected_df

	try:

		# Indexing the metrics to get the abbreviations
		selected_metric_abbr = get_data.getlist("metrics[]", None)

		# Retrive additional parameters if they exist
		# Retrieving the extra optional parameters
		extra_param_dict = {}

		if request.GET.get('mase_m', None) is not None:
			mase_m = float(request.GET.get('mase_m', None))
			extra_param_dict['mase_m'] = mase_m
		else:
			mase_m = 1
			extra_param_dict['mase_m'] = mase_m

		if request.GET.get('dmod_j', None) is not None:
			dmod_j = float(request.GET.get('dmod_j', None))
			extra_param_dict['dmod_j'] = dmod_j
		else:
			dmod_j = 1
			extra_param_dict['dmod_j'] = dmod_j

		if request.GET.get('nse_mod_j', None) is not None:
			nse_mod_j = float(request.GET.get('nse_mod_j', None))
			extra_param_dict['nse_mod_j'] = nse_mod_j
		else:
			nse_mod_j = 1
			extra_param_dict['nse_mod_j'] = nse_mod_j

		if request.GET.get('h6_k_MHE', None) is not None:
			h6_mhe_k = float(request.GET.get('h6_k_MHE', None))
			extra_param_dict['h6_mhe_k'] = h6_mhe_k
		else:
			h6_mhe_k = 1
			extra_param_dict['h6_mhe_k'] = h6_mhe_k

		if request.GET.get('h6_k_AHE', None) is not None:
			h6_ahe_k = float(request.GET.get('h6_k_AHE', None))
			extra_param_dict['h6_ahe_k'] = h6_ahe_k
		else:
			h6_ahe_k = 1
			extra_param_dict['h6_ahe_k'] = h6_ahe_k

		if request.GET.get('h6_k_RMSHE', None) is not None:
			h6_rmshe_k = float(request.GET.get('h6_k_RMSHE', None))
			extra_param_dict['h6_rmshe_k'] = h6_rmshe_k
		else:
			h6_rmshe_k = 1
			extra_param_dict['h6_rmshe_k'] = h6_rmshe_k

		if float(request.GET.get('lm_x_bar', None)) != 1:
			lm_x_bar_p = float(request.GET.get('lm_x_bar', None))
			extra_param_dict['lm_x_bar_p'] = lm_x_bar_p
		else:
			lm_x_bar_p = None
			extra_param_dict['lm_x_bar_p'] = lm_x_bar_p

		if float(request.GET.get('d1_p_x_bar', None)) != 1:
			d1_p_x_bar_p = float(request.GET.get('d1_p_x_bar', None))
			extra_param_dict['d1_p_x_bar_p'] = d1_p_x_bar_p
		else:
			d1_p_x_bar_p = None
			extra_param_dict['d1_p_x_bar_p'] = d1_p_x_bar_p

		'''Merge Data'''
		merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)
		merged_df2 = hd.merge_data(sim_df=corrected_df, obs_df=observed_df)

		'''Plotting Data'''

		# Creating the Table Based on User Input
		table = hs.make_table(
			merged_dataframe = merged_df,
			metrics = selected_metric_abbr,
			# remove_neg=remove_neg,
			# remove_zero=remove_zero,
			mase_m =  extra_param_dict['mase_m'],
			dmod_j = extra_param_dict['dmod_j'],
			nse_mod_j = extra_param_dict['nse_mod_j'],
			h6_mhe_k = extra_param_dict['h6_mhe_k'],
			h6_ahe_k = extra_param_dict['h6_ahe_k'],
			h6_rmshe_k= extra_param_dict['h6_rmshe_k'],
			d1_p_obs_bar_p= extra_param_dict['d1_p_x_bar_p'],
			lm_x_obs_bar_p= extra_param_dict['lm_x_bar_p'],
			# seasonal_periods=all_date_range_list
		)
		table = table.round(decimals=2)
		table_html = table.transpose()
		table_html = table_html.to_html(classes="table table-hover table-striped").replace('border="1"', 'border="0"')

		# Creating the Table Based on User Input
		table2 = hs.make_table(
			merged_dataframe = merged_df2,
			metrics= selected_metric_abbr,
			# remove_neg=remove_neg,
			# remove_zero=remove_zero,
			mase_m= extra_param_dict['mase_m'],
			dmod_j= extra_param_dict['dmod_j'],
			nse_mod_j= extra_param_dict['nse_mod_j'],
			h6_mhe_k= extra_param_dict['h6_mhe_k'],
			h6_ahe_k= extra_param_dict['h6_ahe_k'],
			h6_rmshe_k= extra_param_dict['h6_rmshe_k'],
			d1_p_obs_bar_p= extra_param_dict['d1_p_x_bar_p'],
			lm_x_obs_bar_p= extra_param_dict['lm_x_bar_p'],
			# seasonal_periods=all_date_range_list
		)
		table2 = table2.round(decimals =2)
		table_html2 = table2.transpose()
		table_html2 = table_html2.to_html(classes="table table-hover table-striped").replace('border="1"', 'border="0"')

		table2 = table2.rename(index={'Full Time Series': 'Corrected Full Time Series'})
		table = table.rename(index={'Full Time Series': 'Original Full Time Series'})
		table_html2 = table2.transpose()
		table_html1 = table.transpose()

		table_final = pd.merge(table_html1, table_html2, right_index=True, left_index=True)

		table_final_html = table_final.to_html(classes="table table-hover table-striped",
											   table_id="corrected_1").replace('border="1"', 'border="0"')

		return HttpResponse(table_final_html)

	except Exception:
		traceback.print_exc()
		return JsonResponse({'error': 'No data found for the selected station.'})


def get_units_title(unit_type):
	"""
	Get the title for units
	"""
	units_title = "m"
	if unit_type == 'english':
		units_title = "ft"
	return units_title


def get_time_series(request):
	get_data = request.GET
	global comid
	global codEstacion
	global nomEstacion
	global forecast_df
	global forecast_record

	try:

		hydroviewer_figure = geoglows.plots.forecast_stats(stats=forecast_df, titles={'Station': nomEstacion + '-' + str(codEstacion), 'Reach ID': comid})

		x_vals = (forecast_df.index[0], forecast_df.index[len(forecast_df.index) - 1], forecast_df.index[len(forecast_df.index) - 1], forecast_df.index[0])
		max_visible = max(forecast_df.max())

		'''Getting forecast record'''

		try:

			if len(forecast_record.index) > 0:
				hydroviewer_figure.add_trace(go.Scatter(
					name='1st days forecasts',
					x=forecast_record.index,
					y=forecast_record.iloc[:, 0].values,
					line=dict(
						color='#FFA15A',
					)
				))

			if 'x_vals' in locals():
				x_vals = (forecast_record.index[0], forecast_df.index[len(forecast_df.index) - 1], forecast_df.index[len(forecast_df.index) - 1], forecast_record.index[0])
			else:
				x_vals = (forecast_record.index[0], forecast_df.index[len(forecast_df.index) - 1], forecast_df.index[len(forecast_df.index) - 1], forecast_record.index[0])
				max_visible = max(forecast_record.max(), max_visible)

		except:
			print('Not forecast record for the selected station')

		'''Getting real time observed data'''
		url_rt = 'http://fews.ideam.gov.co/colombia/jsonQ/00' + codEstacion + 'Qobs.json'
		f = requests.get(url_rt, verify=False)

		if f.status_code == 200:
			data = f.json()

			observedDischarge = (data.get('obs'))
			sensorDischarge = (data.get('sen'))

			observedDischarge = (observedDischarge.get('data'))
			sensorDischarge = (sensorDischarge.get('data'))

			datesObservedDischarge = [row[0] for row in observedDischarge]
			observedDischarge = [row[1] for row in observedDischarge]

			datesSensorDischarge = [row[0] for row in sensorDischarge]
			sensorDischarge = [row[1] for row in sensorDischarge]

			dates = []
			discharge = []

			for i in range(0, len(datesObservedDischarge) - 1):
				year = int(datesObservedDischarge[i][0:4])
				month = int(datesObservedDischarge[i][5:7])
				day = int(datesObservedDischarge[i][8:10])
				hh = int(datesObservedDischarge[i][11:13])
				mm = int(datesObservedDischarge[i][14:16])
				dates.append(dt.datetime(year, month, day, hh, mm))
				discharge.append(observedDischarge[i])

			datesObservedDischarge = dates
			observedDischarge = discharge

			dates = []
			discharge = []

			for i in range(0, len(datesSensorDischarge) - 1):
				year = int(datesSensorDischarge[i][0:4])
				month = int(datesSensorDischarge[i][5:7])
				day = int(datesSensorDischarge[i][8:10])
				hh = int(datesSensorDischarge[i][11:13])
				mm = int(datesSensorDischarge[i][14:16])
				dates.append(dt.datetime(year, month, day, hh, mm))
				discharge.append(sensorDischarge[i])

			datesSensorDischarge = dates
			sensorDischarge = discharge

			try:
				# convert request into pandas DF
				pairs = [list(a) for a in zip(datesObservedDischarge, observedDischarge)]
				observed_rt = pd.DataFrame(pairs, columns=['Datetime', 'Observed (m3/s)'])
				observed_rt.set_index('Datetime', inplace=True)
				observed_rt = observed_rt.dropna()
				#observed_rt = observed_rt.groupby(observed_rt.index.strftime("%Y/%m/%d")).mean()
				observed_rt.index = pd.to_datetime(observed_rt.index)
				observed_rt.index = observed_rt.index.tz_localize('UTC')
				observed_rt = observed_rt.loc[observed_rt.index >= pd.to_datetime(forecast_df.index[0] - dt.timedelta(days=8))]
				observed_rt = observed_rt.dropna()

				if len(observed_rt.index) > 0:
					hydroviewer_figure.add_trace(go.Scatter(
						name='Observed Streamflow',
						x=observed_rt.index,
						y=observed_rt.iloc[:, 0].values,
						line=dict(
							color='green',
						)
					))

				if 'forecast_record' in locals():
					x_vals = x_vals
				else:
					x_vals = (observed_rt.index[0], forecast_df.index[len(forecast_df.index) - 1], forecast_df.index[len(forecast_df.index) - 1], observed_rt.index[0])

				max_visible = max(observed_rt.max(), max_visible)

			except:
				print('Not observed data for the selected station')

			try:
				# convert request into pandas DF
				pairs = [list(a) for a in zip(datesSensorDischarge, sensorDischarge)]
				sensor_rt = pd.DataFrame(pairs, columns=['Datetime', 'Sensor (m3/s)'])
				sensor_rt.set_index('Datetime', inplace=True)
				sensor_rt = sensor_rt.dropna()
				#sensor_rt = sensor_rt.groupby(sensor_rt.index.strftime("%Y/%m/%d")).mean()
				sensor_rt.index = pd.to_datetime(sensor_rt.index)
				sensor_rt.index = sensor_rt.index.tz_localize('UTC')
				sensor_rt = sensor_rt.loc[sensor_rt.index >= pd.to_datetime(forecast_df.index[0] - dt.timedelta(days=8))]
				sensor_rt = sensor_rt.dropna()

				if len(sensor_rt.index) > 0:
					hydroviewer_figure.add_trace(go.Scatter(
						name='Sensor Streamflow',
						x=sensor_rt.index,
						y=sensor_rt.iloc[:, 0].values,
						line=dict(
							color='yellow',
						)
					))

				if 'forecast_record' in locals():
					x_vals = x_vals
				elif 'observed_rt' in locals():
					x_vals = x_vals
				else:
					x_vals = (sensor_rt.index[0], forecast_df.index[len(forecast_df.index) - 1], forecast_df.index[len(forecast_df.index) - 1], sensor_rt.index[0])

				max_visible = max(sensor_rt.max(), max_visible)

			except:
				print('Not sensor data for the selected station')

		'''Getting Return Periods'''

		try:
			rperiods = geoglows.streamflow.return_periods(comid)

			r2 = int(rperiods.iloc[0]['return_period_2'])

			colors = {
				'2 Year': 'rgba(254, 240, 1, .4)',
				'5 Year': 'rgba(253, 154, 1, .4)',
				'10 Year': 'rgba(255, 56, 5, .4)',
				'20 Year': 'rgba(128, 0, 246, .4)',
				'25 Year': 'rgba(255, 0, 0, .4)',
				'50 Year': 'rgba(128, 0, 106, .4)',
				'100 Year': 'rgba(128, 0, 246, .4)',
			}

			if max_visible > r2:
				visible = True
				hydroviewer_figure.for_each_trace(
					lambda trace: trace.update(visible=True) if trace.name == "Maximum & Minimum Flow" else (),
				)
			else:
				visible = 'legendonly'
				hydroviewer_figure.for_each_trace(
					lambda trace: trace.update(visible=True) if trace.name == "Maximum & Minimum Flow" else (),
				)

			def template(name, y, color, fill='toself'):
				return go.Scatter(
					name=name,
					x=x_vals,
					y=y,
					legendgroup='returnperiods',
					fill=fill,
					visible=visible,
					line=dict(color=color, width=0))

			r5 = int(rperiods.iloc[0]['return_period_5'])
			r10 = int(rperiods.iloc[0]['return_period_10'])
			r25 = int(rperiods.iloc[0]['return_period_25'])
			r50 = int(rperiods.iloc[0]['return_period_50'])
			r100 = int(rperiods.iloc[0]['return_period_100'])

			hydroviewer_figure.add_trace(template('Return Periods', (r100 * 0.05, r100 * 0.05, r100 * 0.05, r100 * 0.05), 'rgba(0,0,0,0)', fill='none'))
			hydroviewer_figure.add_trace(template(f'2 Year: {r2}', (r2, r2, r5, r5), colors['2 Year']))
			hydroviewer_figure.add_trace(template(f'5 Year: {r5}', (r5, r5, r10, r10), colors['5 Year']))
			hydroviewer_figure.add_trace(template(f'10 Year: {r10}', (r10, r10, r25, r25), colors['10 Year']))
			hydroviewer_figure.add_trace(template(f'25 Year: {r25}', (r25, r25, r50, r50), colors['25 Year']))
			hydroviewer_figure.add_trace(template(f'50 Year: {r50}', (r50, r50, r100, r100), colors['50 Year']))
			hydroviewer_figure.add_trace(template(f'100 Year: {r100}', (r100, r100, max(r100 + r100 * 0.05, max_visible), max(r100 + r100 * 0.05, max_visible)),colors['100 Year']))

		except:
			print('There is no return periods for the desired stream')

		chart_obj = PlotlyView(hydroviewer_figure)

		context = {
			'gizmo_object': chart_obj,
		}

		return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected reach.'})



def get_time_series_bc(request):
	get_data = request.GET
	global comid
	global codEstacion
	global nomEstacion
	global corrected_df
	global forecast_df
	global fixed_stats
	global forecast_record
	global fixed_records

	try:

		hydroviewer_figure = geoglows.plots.forecast_stats(stats=fixed_stats, titles={'Station': nomEstacion + '-' + str(codEstacion), 'Reach ID': comid, 'bias_corrected': True})

		x_vals = (fixed_stats.index[0], fixed_stats.index[len(fixed_stats.index) - 1], fixed_stats.index[len(fixed_stats.index) - 1], fixed_stats.index[0])
		max_visible = max(fixed_stats.max())

		'''Getting forecast record'''

		try:

			if len(fixed_records.index) > 0:
				hydroviewer_figure.add_trace(go.Scatter(
					name='1st days forecasts',
					x=fixed_records.index,
					y=fixed_records.iloc[:, 0].values,
					line=dict(
						color='#FFA15A',
					)
				))

			if 'x_vals' in locals():
				x_vals = (fixed_records.index[0], fixed_stats.index[len(fixed_stats.index) - 1], fixed_stats.index[len(fixed_stats.index) - 1], fixed_records.index[0])
			else:
				x_vals = (fixed_records.index[0], fixed_stats.index[len(fixed_stats.index) - 1], fixed_stats.index[len(fixed_stats.index) - 1], fixed_records.index[0])

			max_visible = max(fixed_records.max(), max_visible)

		except:
			print('There is no forecast record')

		# Getting real time observed data
		url_rt = 'http://fews.ideam.gov.co/colombia/jsonQ/00' + codEstacion + 'Qobs.json'
		f = requests.get(url_rt, verify=False)

		if f.status_code == 200:
			data = f.json()

			observedDischarge = (data.get('obs'))
			sensorDischarge = (data.get('sen'))

			observedDischarge = (observedDischarge.get('data'))
			sensorDischarge = (sensorDischarge.get('data'))

			datesObservedDischarge = [row[0] for row in observedDischarge]
			observedDischarge = [row[1] for row in observedDischarge]

			datesSensorDischarge = [row[0] for row in sensorDischarge]
			sensorDischarge = [row[1] for row in sensorDischarge]

			dates = []
			discharge = []

			for i in range(0, len(datesObservedDischarge) - 1):
				year = int(datesObservedDischarge[i][0:4])
				month = int(datesObservedDischarge[i][5:7])
				day = int(datesObservedDischarge[i][8:10])
				hh = int(datesObservedDischarge[i][11:13])
				mm = int(datesObservedDischarge[i][14:16])
				dates.append(dt.datetime(year, month, day, hh, mm))
				discharge.append(observedDischarge[i])

			datesObservedDischarge = dates
			observedDischarge = discharge

			dates = []
			discharge = []

			for i in range(0, len(datesSensorDischarge) - 1):
				year = int(datesSensorDischarge[i][0:4])
				month = int(datesSensorDischarge[i][5:7])
				day = int(datesSensorDischarge[i][8:10])
				hh = int(datesSensorDischarge[i][11:13])
				mm = int(datesSensorDischarge[i][14:16])
				dates.append(dt.datetime(year, month, day, hh, mm))
				discharge.append(sensorDischarge[i])

			datesSensorDischarge = dates
			sensorDischarge = discharge

			try:
				# convert request into pandas DF
				pairs = [list(a) for a in zip(datesObservedDischarge, observedDischarge)]
				observed_rt = pd.DataFrame(pairs, columns=['Datetime', 'Observed (m3/s)'])
				observed_rt.set_index('Datetime', inplace=True)
				observed_rt = observed_rt.dropna()
				#observed_rt = observed_rt.groupby(observed_rt.index.strftime("%Y/%m/%d")).mean()
				observed_rt.index = pd.to_datetime(observed_rt.index)
				observed_rt.index = observed_rt.index.tz_localize('UTC')
				observed_rt = observed_rt.loc[
					observed_rt.index >= pd.to_datetime(forecast_df.index[0] - dt.timedelta(days=8))]
				observed_rt = observed_rt.dropna()

				if len(observed_rt.index) > 0:
					hydroviewer_figure.add_trace(go.Scatter(
						name='Observed Streamflow',
						x=observed_rt.index,
						y=observed_rt.iloc[:, 0].values,
						line=dict(
							color='green',
						)
					))

				if 'fixed_records' in locals():
					x_vals = x_vals
				else:
					x_vals = (observed_rt.index[0], fixed_stats.index[len(fixed_stats.index) - 1], fixed_stats.index[len(fixed_stats.index) - 1], observed_rt.index[0])

				max_visible = max(observed_rt.max(), max_visible)

			except:
				print('Not observed data for the selected station')

			try:
				# convert request into pandas DF
				pairs = [list(a) for a in zip(datesSensorDischarge, sensorDischarge)]
				sensor_rt = pd.DataFrame(pairs, columns=['Datetime', 'Sensor (m3/s)'])
				sensor_rt.set_index('Datetime', inplace=True)
				sensor_rt = sensor_rt.dropna()
				#sensor_rt = sensor_rt.groupby(sensor_rt.index.strftime("%Y/%m/%d")).mean()
				sensor_rt.index = pd.to_datetime(sensor_rt.index)
				sensor_rt.index = sensor_rt.index.tz_localize('UTC')
				sensor_rt = sensor_rt.loc[
					sensor_rt.index >= pd.to_datetime(forecast_df.index[0] - dt.timedelta(days=8))]
				sensor_rt = sensor_rt.dropna()

				if len(sensor_rt.index) > 0:
					hydroviewer_figure.add_trace(go.Scatter(
						name='Sensor Streamflow',
						x=sensor_rt.index,
						y=sensor_rt.iloc[:, 0].values,
						line=dict(
							color='yellow',
						)
					))

				if 'fixed_records' in locals():
					x_vals = x_vals
				elif 'observed_rt' in locals():
					x_vals = x_vals
				else:
					x_vals = (sensor_rt.index[0], fixed_stats.index[len(fixed_stats.index) - 1], fixed_stats.index[len(fixed_stats.index) - 1], sensor_rt.index[0])

				max_visible = max(sensor_rt.max(), max_visible)

			except:
				print('Not sensor data for the selected station')

		'''Getting Corrected Return Periods'''
		max_annual_flow = corrected_df.groupby(corrected_df.index.strftime("%Y")).max()
		mean_value = np.mean(max_annual_flow.iloc[:,0].values)
		std_value = np.std(max_annual_flow.iloc[:,0].values)

		return_periods = [100, 50, 25, 10, 5, 2]

		def gumbel_1(std: float, xbar: float, rp: int or float) -> float:
			"""
			Solves the Gumbel Type I probability distribution function (pdf) = exp(-exp(-b)) where b is the covariate. Provide
			the standard deviation and mean of the list of annual maximum flows. Compare scipy.stats.gumbel_r
			Args:
				std (float): the standard deviation of the series
				xbar (float): the mean of the series
				rp (int or float): the return period in years
			Returns:
				float, the flow corresponding to the return period specified
			"""
			# xbar = statistics.mean(year_max_flow_list)
			# std = statistics.stdev(year_max_flow_list, xbar=xbar)
			return -math.log(-math.log(1 - (1 / rp))) * std * .7797 + xbar - (.45 * std)

		return_periods_values = []

		for rp in return_periods:
			return_periods_values.append(gumbel_1(std_value, mean_value, rp))

		d = {'rivid': [comid], 'return_period_100': [return_periods_values[0]], 'return_period_50': [return_periods_values[1]], 'return_period_25': [return_periods_values[2]], 'return_period_10': [return_periods_values[3]], 'return_period_5': [return_periods_values[4]], 'return_period_2': [return_periods_values[5]]}
		rperiods = pd.DataFrame(data=d)
		rperiods.set_index('rivid', inplace=True)

		r2 = int(rperiods.iloc[0]['return_period_2'])

		colors = {
			'2 Year': 'rgba(254, 240, 1, .4)',
			'5 Year': 'rgba(253, 154, 1, .4)',
			'10 Year': 'rgba(255, 56, 5, .4)',
			'20 Year': 'rgba(128, 0, 246, .4)',
			'25 Year': 'rgba(255, 0, 0, .4)',
			'50 Year': 'rgba(128, 0, 106, .4)',
			'100 Year': 'rgba(128, 0, 246, .4)',
		}

		if max_visible > r2:
			visible = True
			hydroviewer_figure.for_each_trace(
				lambda trace: trace.update(visible=True) if trace.name == "Maximum & Minimum Flow" else (),
			)
		else:
			visible = 'legendonly'
			hydroviewer_figure.for_each_trace(
				lambda trace: trace.update(visible=True) if trace.name == "Maximum & Minimum Flow" else (),
			)

		def template(name, y, color, fill='toself'):
			return go.Scatter(
				name=name,
				x=x_vals,
				y=y,
				legendgroup='returnperiods',
				fill=fill,
				visible=visible,
				line=dict(color=color, width=0))

		r5 = int(rperiods.iloc[0]['return_period_5'])
		r10 = int(rperiods.iloc[0]['return_period_10'])
		r25 = int(rperiods.iloc[0]['return_period_25'])
		r50 = int(rperiods.iloc[0]['return_period_50'])
		r100 = int(rperiods.iloc[0]['return_period_100'])

		hydroviewer_figure.add_trace(template('Return Periods', (r100 * 0.05, r100 * 0.05, r100 * 0.05, r100 * 0.05), 'rgba(0,0,0,0)', fill='none'))
		hydroviewer_figure.add_trace(template(f'2 Year: {r2}', (r2, r2, r5, r5), colors['2 Year']))
		hydroviewer_figure.add_trace(template(f'5 Year: {r5}', (r5, r5, r10, r10), colors['5 Year']))
		hydroviewer_figure.add_trace(template(f'10 Year: {r10}', (r10, r10, r25, r25), colors['10 Year']))
		hydroviewer_figure.add_trace(template(f'25 Year: {r25}', (r25, r25, r50, r50), colors['25 Year']))
		hydroviewer_figure.add_trace(template(f'50 Year: {r50}', (r50, r50, r100, r100), colors['50 Year']))
		hydroviewer_figure.add_trace(template(f'100 Year: {r100}', (r100, r100, max(r100 + r100 * 0.05, max_visible), max(r100 + r100 * 0.05, max_visible)), colors['100 Year']))

		chart_obj = PlotlyView(hydroviewer_figure)

		context = {
			'gizmo_object': chart_obj,
		}

		return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No data found for the selected reach.'})


def get_observed_discharge_csv(request):
	"""
	Get observed data from csv files in Hydroshare
	"""

	get_data = request.GET
	global observed_df
	global codEstacion
	global nomEstacion

	try:

		datesObservedDischarge = observed_df.index.tolist()
		observedDischarge = observed_df.iloc[:, 0].values
		observedDischarge.tolist()

		pairs = [list(a) for a in zip(datesObservedDischarge, observedDischarge)]

		response = HttpResponse(content_type='text/csv')
		response['Content-Disposition'] = 'attachment; filename=observed_discharge_{0}.csv'.format(codEstacion)

		writer = csv_writer(response)
		writer.writerow(['datetime', 'Observed Streamflow (m3/s)'])

		for row_data in pairs:
			writer.writerow(row_data)

		return response

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'An unknown error occurred while retrieving the Discharge Data.'})


def get_simulated_discharge_csv(request):
	"""
	Get historic simulations from ERA Interim
	"""
	get_data = request.GET
	global comid
	global codEstacion
	global nomEstacion
	global simulated_df

	try:

		pairs = [list(a) for a in zip(simulated_df.index, simulated_df.iloc[:, 0])]

		response = HttpResponse(content_type='text/csv')
		response['Content-Disposition'] = 'attachment; filename=simulated_discharge_{0}.csv'.format(codEstacion)

		writer = csv_writer(response)
		writer.writerow(['datetime', 'Simulated Streamflow (m3/s)'])

		for row_data in pairs:
			writer.writerow(row_data)

		return response

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'An unknown error occurred while retrieving the Discharge Data.'})


def get_simulated_bc_discharge_csv(request):
	"""
	Get historic simulations from ERA Interim
	"""

	get_data = request.GET
	global comid
	global codEstacion
	global nomEstacion
	global observed_df
	global simulated_df
	global corrected_df

	try:

		response = HttpResponse(content_type='text/csv')
		response['Content-Disposition'] = 'attachment; filename=corrected_simulated_discharge_{0}.csv'.format(
			codEstacion)

		corrected_df.to_csv(encoding='utf-8', header=True, path_or_buf=response)

		return response

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'An unknown error occurred while retrieving the Discharge Data.'})


def get_forecast_data_csv(request):
	"""""
	Returns Forecast data as csv
	"""""

	get_data = request.GET
	global watershed
	global subbasin
	global comid
	global forecast_df

	try:

		# Writing CSV
		response = HttpResponse(content_type='text/csv')
		response['Content-Disposition'] = 'attachment; filename=streamflow_forecast_{0}_{1}_{2}.csv'.format(watershed, subbasin, comid)

		forecast_df.to_csv(encoding='utf-8', header=True, path_or_buf=response)

		return response

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No forecast data found.'})


def get_forecast_bc_data_csv(request):
	"""""
	Returns Forecast data as csv
	"""""

	get_data = request.GET
	global watershed
	global subbasin
	global comid
	global forecast_df
	global fixed_stats

	try:

		response = HttpResponse(content_type='text/csv')
		response['Content-Disposition'] = 'attachment; filename=corrected_streamflow_forecast_{0}_{1}_{2}.csv'.format(watershed, subbasin, comid)

		fixed_stats.to_csv(encoding='utf-8', header=True, path_or_buf=response)

		return response

	except Exception as e:
		print(str(e))
		return JsonResponse({'error': 'No forecast data found.'})
