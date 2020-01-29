from typing import Dict

import numpy as np
import pandas

from hts.core.types import NAryTreeT


def to_sum_mat(ntree: NAryTreeT):
    """
    This function creates a summing matrix for the bottom up and optimal combination approaches
    All the inputs are the same as above
    The output is a summing matrix, see Rob Hyndman's "Forecasting: principles and practice" Section 9.4

    Parameters
    ----------
    ntree

    Returns
    -------

    """
    nodes = ntree.level_order_traversal()
    num_at_level = list(map(sum, nodes))
    columns = num_at_level[-1]
    bl_mat = np.identity(columns)
    top = np.ones(columns)
    final_mat = bl_mat
    num_levels = len(num_at_level)

    for lev in range(num_levels - 1):
        summing = nodes[-(lev + 1)]
        count = 0
        num2sum_ind = 0
        B = np.zeros([num_at_level[-1]])
        for num2sum in summing:
            num2sum_ind += num2sum
            a = bl_mat[count:num2sum_ind, :]
            count += num2sum
            if np.all(B == 0):
                B = a.sum(axis=0)
            else:
                B = np.vstack((B, a.sum(axis=0)))
        final_mat = np.vstack((B, final_mat))
        bl_mat = B

    final_mat = np.vstack((top, final_mat))
    return final_mat


def project(hat_mat: np.ndarray, sum_mat: np.ndarray, optimal_mat: np.ndarray) -> np.ndarray:
    new_mat = np.empty([hat_mat.shape[0], sum_mat.shape[0]])
    for i in range(hat_mat.shape[0]):
        new_mat[i, :] = np.dot(optimal_mat, np.transpose(hat_mat[i, :]))
    return new_mat


def y_hat_matrix(forecasts, keys=None):
    if not keys:
        keys = forecasts.keys()
    first = list(forecasts.keys())[0]
    y_hat_mat = np.zeros([len(forecasts[first].yhat), 1])
    for key in keys:
        f1 = np.array(forecasts[key].yhat)
        f2 = f1[:, np.newaxis]
        if np.all(y_hat_mat == 0):
            y_hat_mat = f2
        else:
            y_hat_mat = np.concatenate((y_hat_mat, f2), axis=1)
    return y_hat_mat


def optimal_combination(forecasts: Dict[str, pandas.DataFrame], sum_mat: np.ndarray, method: str, mse: Dict[str, float]):
    """
    Produces the optimal combination of forecasts by trace minimization (as described by
    Wickramasuriya, Athanasopoulos, Hyndman in "Optimal Forecast Reconciliation for Hierarchical and Grouped Time
    Series Through Trace Minimization")

    Parameters
    ----------
    forecasts : dict
        Dictionary of pandas.DataFrames containing the future predictions
    sum_mat : np.ndarray
        The summing  matrix
    method : str
        One of:
            - OLS (ordinary least squares)
            - WLSS (structurally weighted least squares)
            - WLSV (variance weighted least squares)
    mse

    Returns
    -------

    """
    hat_mat = y_hat_matrix(forecasts)
    transpose = np.transpose(sum_mat)

    if method == 'OLS':
        ols = np.dot(np.dot(sum_mat, np.linalg.inv(np.dot(transpose, sum_mat))), transpose)
        return project(hat_mat=hat_mat, sum_mat=sum_mat, optimal_mat=ols)
    elif method == 'WLSS':
        diag = np.diag(np.transpose(np.sum(sum_mat, axis=1)))
    elif method == 'WLSV':
        diag = [mse[key] for key in mse.keys()]
        diag = np.diag(np.flip(np.hstack(diag) + 0.0000001, 0))
    else:
        raise ValueError('Invalid method')

    # S*inv(S'S)*S'
    optimal_mat = np.dot(
        np.dot(np.dot(sum_mat, np.linalg.inv(np.dot(np.dot(transpose, np.linalg.inv(diag)), sum_mat))),
               transpose), np.linalg.inv(diag))

    return project(hat_mat=hat_mat, sum_mat=sum_mat, optimal_mat=optimal_mat)


def proportions(df, forecasts, sum_mat, method='APH'):
    n_cols = len(list(forecasts.keys())) + 1
    fcst = forecasts[0].yhat
    fcst = fcst[:, np.newaxis]
    num_bts = sum_mat.shape[1]
    bts_dat = pandas.DataFrame(df.iloc[:, n_cols - num_bts:n_cols])
    if method == 'APH':
        divs = np.divide(np.transpose(np.array(bts_dat)), np.array(df.iloc[:, 1]))
        props = divs.mean(1)
        props = props[:, np.newaxis]
    elif method == 'PHA':
        bts_sum = bts_dat.sum(0)
        top_sum = sum(df.iloc[:, 1])
        props = bts_sum / top_sum
        props = props[:, np.newaxis]
    else:
        raise ValueError('Invalid method')
    return np.dot(np.array(fcst), np.transpose(props))


def forecast_proportions(forecasts, nodes):
    """
    Cons:
       Produces biased revised forecasts even if base forecasts are unbiased
    """
    n_cols = len(list(forecasts.keys())) + 1
    ##
    # Find proportions of forecast at each step ahead, and then alter forecasts
    ##
    levels = len(nodes)
    column = 0
    first_node = 1
    new_mat = np.empty([len(forecasts[0].yhat), n_cols - 1])
    new_mat[:, 0] = forecasts[0].yhat
    for level in range(levels):
        nodes_in_level = len(nodes[level])
        for node in range(nodes_in_level):
            num_child = nodes[level][node]
            last_node = first_node + num_child
            lst = [x for x in range(first_node, last_node)]
            base_fcst = np.array([forecasts[k].yhat[:] for k in lst])
            fore_sum = np.sum(base_fcst, axis=0)
            fore_sum = fore_sum[:, np.newaxis]
            if column == 0:
                rev_top = np.array(forecasts[column].yhat)
                rev_top = rev_top[:, np.newaxis]
            else:
                rev_top = np.array(new_mat[:, column])
                rev_top = rev_top[:, np.newaxis]
            new_mat[:, first_node:last_node] = np.divide(np.multiply(np.transpose(base_fcst), rev_top), fore_sum)
            column += 1
            first_node += num_child
    return new_mat
