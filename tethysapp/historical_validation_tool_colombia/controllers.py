from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from tethys_sdk.gizmos import PlotlyView
from django.http import HttpResponse, JsonResponse

import pandas as pd
import io
import requests
import numpy as np
import datetime as dt
import plotly.graph_objs as go
import hydrostats as hs
import hydrostats.data as hd
from HydroErr.HydroErr import metric_names, metric_abbr
import scipy.stats as sp
from scipy import integrate
import traceback
from csv import writer as csv_writer

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

def get_discharge_data(request):
    """
    Get observed data from csv files in Hydroshare
    """

    get_data = request.GET

    try:

        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_Q = go.Scatter(
            x=datesDischarge,
            y=dataDischarge,
            name='Observed Discharge',
        )

        layout = go.Layout(title='Observed Streamflow {0}-{1}'.format(nomEstacion, codEstacion),
                           xaxis=dict(title='Dates', ), yaxis=dict(title='Discharge (m<sup>3</sup>/s)',
                                                                   autorange=True), showlegend=False)

        chart_obj = PlotlyView(go.Figure(data=[observed_Q], layout=layout))

        context = {
            'gizmo_object': chart_obj,
        }

        return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

    except Exception as e:
        print(str(e))
        return JsonResponse({'error': 'No observed data found for the selected station.'})

def get_simulated_data(request):
    """
    Get simulated data from api
    """

    try:
        get_data = request.GET
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        # ----------------------------------------------
        # Chart Section
        # ----------------------------------------------

        simulated_Q = go.Scatter(
            name='Simulated Discharge',
            x=era_dates,
            y=era_values,
        )

        layout = go.Layout(
            title="Simulated Streamflow at <br> {0}".format(nomEstacion),
            xaxis=dict(title='Date', ), yaxis=dict(title='Discharge (m<sup>3</sup>/s)'),
        )

        chart_obj = PlotlyView(go.Figure(data=[simulated_Q], layout=layout))

        context = {
            'gizmo_object': chart_obj,
        }

        return render(request, 'historical_validation_tool_colombia/gizmo_ajax.html', context)

    except Exception as e:
        print(str(e))
        return JsonResponse({'error': 'No simulated data found for the selected station.'})

def get_hydrographs(request):
    """
    Get observed data from csv files in Hydroshare
    Get historic simulations from ERA Interim
    """
    get_data = request.GET

    try:
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        simulated_df = pd.DataFrame(data=era_values, index=era_dates, columns=['Simulated Streamflow'])

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

        merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

        observed_Q = go.Scatter(x=merged_df.index, y=merged_df.iloc[:, 1].values, name='Observed', )

        simulated_Q = go.Scatter(x=merged_df.index, y=merged_df.iloc[:, 0].values, name='Simulated', )

        layout = go.Layout(
            title='Observed & Simulated Streamflow at <br> {0} - {1}'.format(codEstacion, nomEstacion),
            xaxis=dict(title='Dates', ), yaxis=dict(title='Discharge (m<sup>3</sup>/s)', autorange=True),
            showlegend=True)

        chart_obj = PlotlyView(go.Figure(data=[observed_Q, simulated_Q], layout=layout))

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

    try:
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        simulated_df = pd.DataFrame(data=era_values, index=era_dates, columns=['Simulated Streamflow'])

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

        merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

        daily_avg = hd.daily_average(merged_df)

        daily_avg_obs_Q = go.Scatter(x=daily_avg.index, y=daily_avg.iloc[:, 1].values, name='Observed', )

        daily_avg_sim_Q = go.Scatter(x=daily_avg.index, y=daily_avg.iloc[:, 0].values, name='Simulated', )

        layout = go.Layout(
            title='Daily Average Streamflow for <br> {0} - {1}'.format(codEstacion, nomEstacion),
            xaxis=dict(title='Days', ), yaxis=dict(title='Discharge (m<sup>3</sup>/s)', autorange=True),
            showlegend=True)

        chart_obj = PlotlyView(go.Figure(data=[daily_avg_obs_Q, daily_avg_sim_Q], layout=layout))

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

    try:
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        simulated_df = pd.DataFrame(data=era_values, index=era_dates, columns=['Simulated Streamflow'])

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

        merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

        monthly_avg = hd.monthly_average(merged_df)

        daily_avg_obs_Q = go.Scatter(x=monthly_avg.index, y=monthly_avg.iloc[:, 1].values, name='Observed', )

        daily_avg_sim_Q = go.Scatter(x=monthly_avg.index, y=monthly_avg.iloc[:, 0].values, name='Simulated', )

        layout = go.Layout(
            title='Monthly Average Streamflow for <br> {0} - {1}'.format(codEstacion, nomEstacion),
            xaxis=dict(title='Days', ), yaxis=dict(title='Discharge (m<sup>3</sup>/s)', autorange=True),
            showlegend=True)

        chart_obj = PlotlyView(go.Figure(data=[daily_avg_obs_Q, daily_avg_sim_Q], layout=layout))

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

    try:
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        simulated_df = pd.DataFrame(data=era_values, index=era_dates, columns=['Simulated Streamflow'])

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

        merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

        scatter_data = go.Scatter(
            x=merged_df.iloc[:, 0].values,
            y=merged_df.iloc[:, 1].values,
            mode='markers',
            name=''
        )

        min_value = min(min(merged_df.iloc[:, 1].values), min(merged_df.iloc[:, 0].values))
        max_value = max(max(merged_df.iloc[:, 1].values), max(merged_df.iloc[:, 0].values))

        line_45 = go.Scatter(
            x=[min_value, max_value],
            y=[min_value, max_value],
            mode='lines',
            name='45deg line'
        )

        slope, intercept, r_value, p_value, std_err = sp.linregress(merged_df.iloc[:, 0].values,
                                                                    merged_df.iloc[:, 1].values)

        line_adjusted = go.Scatter(
            x=[min_value, max_value],
            y=[slope * min_value + intercept, slope * max_value + intercept],
            mode='lines',
            name='{0}x + {1}'.format(str(round(slope, 2)), str(round(intercept, 2)))
        )

        layout = go.Layout(title="Scatter Plot for {0} - {1}".format(codEstacion, nomEstacion),
                           xaxis=dict(title='Simulated', ), yaxis=dict(title='Observed', autorange=True),
                           showlegend=True)

        chart_obj = PlotlyView(go.Figure(data=[scatter_data, line_45, line_adjusted], layout=layout))

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

    try:
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        simulated_df = pd.DataFrame(data=era_values, index=era_dates, columns=['Simulated Streamflow'])

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

        merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

        scatter_data = go.Scatter(
            x=merged_df.iloc[:, 0].values,
            y=merged_df.iloc[:, 1].values,
            mode='markers',
            name=''
        )

        min_value = min(min(merged_df.iloc[:, 1].values), min(merged_df.iloc[:, 0].values))
        max_value = max(max(merged_df.iloc[:, 1].values), max(merged_df.iloc[:, 0].values))

        line_45 = go.Scatter(
            x=[min_value, max_value],
            y=[min_value, max_value],
            mode='lines',
            name='45deg line'
        )

        layout = go.Layout(title="Scatter Plot for {0} - {1} (Log Scale)".format(codEstacion, nomEstacion),
                           xaxis=dict(title='Simulated', type='log', ), yaxis=dict(title='Observed', type='log',
                                                                                   autorange=True), showlegend=True)

        chart_obj = PlotlyView(go.Figure(data=[scatter_data, line_45], layout=layout))

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

    try:
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        simulated_df = pd.DataFrame(data=era_values, index=era_dates, columns=['Simulated Streamflow'])

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

        merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

        sim_array = merged_df.iloc[:, 0].values
        obs_array = merged_df.iloc[:, 1].values

        sim_volume_dt = sim_array * 0.0864
        obs_volume_dt = obs_array * 0.0864

        sim_volume_cum = []
        obs_volume_cum = []
        sum_sim = 0
        sum_obs = 0

        for i in sim_volume_dt:
            sum_sim = sum_sim + i
            sim_volume_cum.append(sum_sim)

        for j in obs_volume_dt:
            sum_obs = sum_obs + j
            obs_volume_cum.append(sum_obs)

        observed_volume = go.Scatter(x=merged_df.index, y=obs_volume_cum, name='Observed', )

        simulated_volume = go.Scatter(x=merged_df.index, y=sim_volume_cum, name='Simulated', )

        layout = go.Layout(
            title='Observed & Simulated Volume at<br> {0} - {1}'.format(codEstacion, nomEstacion),
            xaxis=dict(title='Dates', ), yaxis=dict(title='Volume (Mm<sup>3</sup>)', autorange=True),
            showlegend=True)

        chart_obj = PlotlyView(go.Figure(data=[observed_volume, simulated_volume], layout=layout))

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

    try:
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        simulated_df = pd.DataFrame(data=era_values, index=era_dates, columns=['Simulated Streamflow'])

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

        merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

        sim_array = merged_df.iloc[:, 0].values
        obs_array = merged_df.iloc[:, 1].values

        sim_volume = round((integrate.simps(sim_array)) * 0.0864, 3)
        obs_volume = round((integrate.simps(obs_array)) * 0.0864, 3)

        resp = {
            "sim_volume": sim_volume,
            "obs_volume": obs_volume,
        }

        return JsonResponse(resp)

    except Exception as e:
        print(str(e))
        return JsonResponse({'error': 'No data found for the selected station.'})

def make_table_ajax(request):

    get_data = request.GET

    try:
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # Indexing the metrics to get the abbreviations
        selected_metric_abbr = get_data.getlist("metrics[]", None)

        #print(selected_metric_abbr)

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

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/',
                               params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        simulated_df = pd.DataFrame(data=era_values, index=era_dates, columns=['Simulated Streamflow'])

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesDischarge = df.index.tolist()
        dataDischarge = df.iloc[:, 0].values
        dataDischarge.tolist()

        if isinstance(dataDischarge[0], str):
            dataDischarge = map(float, dataDischarge)

        observed_df = pd.DataFrame(data=dataDischarge, index=datesDischarge, columns=['Observed Streamflow'])

        merged_df = hd.merge_data(sim_df=simulated_df, obs_df=observed_df)

        # Creating the Table Based on User Input
        table = hs.make_table(
            merged_dataframe=merged_df,
            metrics=selected_metric_abbr,
            # remove_neg=remove_neg,
            # remove_zero=remove_zero,
            mase_m=extra_param_dict['mase_m'],
            dmod_j=extra_param_dict['dmod_j'],
            nse_mod_j=extra_param_dict['nse_mod_j'],
            h6_mhe_k=extra_param_dict['h6_mhe_k'],
            h6_ahe_k=extra_param_dict['h6_ahe_k'],
            h6_rmshe_k=extra_param_dict['h6_rmshe_k'],
            d1_p_obs_bar_p=extra_param_dict['d1_p_x_bar_p'],
            lm_x_obs_bar_p=extra_param_dict['lm_x_bar_p'],
            # seasonal_periods=all_date_range_list
        )
        table_html = table.transpose()
        table_html = table_html.to_html(classes="table table-hover table-striped").replace('border="1"', 'border="0"')

        return HttpResponse(table_html)

    except Exception:
        traceback.print_exc()
        return JsonResponse({'error': 'No data found for the selected station.'})

def get_observed_discharge_csv(request):
    """
    Get observed data from csv files in Hydroshare
    """

    get_data = request.GET

    try:
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        url = 'https://www.hydroshare.org/resource/d222676fbd984a81911761ca1ba936bf/data/contents/Discharge_Data/{0}.csv'.format(codEstacion)

        s = requests.get(url).content

        df = pd.read_csv(io.StringIO(s.decode('utf-8')), index_col=0, skiprows=26)
        df.index = pd.to_datetime(df.index)

        datesObservedDischarge = df.index.tolist()
        observedDischarge = df.iloc[:, 0].values
        observedDischarge.tolist()

        pairs = [list(a) for a in zip(datesObservedDischarge, observedDischarge)]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=observed_discharge_{0}.csv'.format(codEstacion)

        writer = csv_writer(response)
        writer.writerow(['datetime', 'flow (m3/s)'])

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

    try:
        get_data = request.GET
        watershed = get_data['watershed']
        subbasin = get_data['subbasin']
        comid = get_data['streamcomid']
        codEstacion = get_data['stationcode']
        nomEstacion = get_data['stationname']

        # request_params
        request_params = dict(watershed_name=watershed, subbasin_name=subbasin, reach_id=comid, return_format='csv')

        # Token is for the demo account
        request_headers = dict(Authorization='Token 1adf07d983552705cd86ac681f3717510b6937f6')

        era_res = requests.get('https://tethys2.byu.edu/apps/streamflow-prediction-tool/api/GetHistoricData/', params=request_params, headers=request_headers)

        era_pairs = era_res.content.splitlines()
        era_pairs.pop(0)

        era_dates = []
        era_values = []

        for era_pair in era_pairs:
            era_pair = era_pair.decode('utf-8')
            era_dates.append(dt.datetime.strptime(era_pair.split(',')[0], '%Y-%m-%d %H:%M:%S'))
            era_values.append(float(era_pair.split(',')[1]))

        pairs = [list(a) for a in zip(era_dates, era_values)]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=simulated_discharge_{0}.csv'.format(codEstacion)

        writer = csv_writer(response)
        writer.writerow(['datetime', 'flow (m3/s)'])

        for row_data in pairs:
            writer.writerow(row_data)

        return response

    except Exception as e:
        print(str(e))
        return JsonResponse({'error': 'An unknown error occurred while retrieving the Discharge Data.'})