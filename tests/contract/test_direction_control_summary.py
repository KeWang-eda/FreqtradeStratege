"""The primary metric is a row-count ratio, including with missing DI coverage."""
import numpy as np
import pandas as pd
import pytest

from tools.summarize_direction_control import compare

pytestmark=pytest.mark.unit_contract


def sample():
    rows=[]
    for day in range(2):
        for pair in ['BTC','ETH','BNB']:
            for arm in ['base','candidate']:
                rows.append({'period':'fold0','date':pd.Timestamp('2024-01-01',tz='UTC')+pd.Timedelta(days=day),
                    'pair':pair,'truth':1.,'ready':int(day==0 or pair=='BTC'),'arm':arm,
                    'prediction':float((day==0)==(arm=='candidate'))*2-1})
    return pd.DataFrame(rows)


def test_missing_coin_coverage_uses_eligible_count_not_average_date_mean():
    result=compare(sample(),'base','candidate',draws=100)
    assert result['all_n']==6 and result['ready_n']==4
    assert result['masks']['all']['delta']==0.
    assert result['masks']['ready']['delta']==.5
    assert result['masks']['ready']['baseline_correct']==1
    assert result['masks']['ready']['candidate_correct']==3
    # Two dates drawn cyclically in every block preserve a 3:1 ready ratio.
    assert result['masks']['ready']['date_block_ci95']['6']==[.5,.5]


def test_true_zero_is_not_dropped_or_encoded_negative_for_scoring():
    data=sample()
    idx=(data.date==data.date.min())&(data.pair=='BTC')
    data.loc[idx,'truth']=0.
    data.loc[idx&(data.arm=='candidate'),'prediction']=0.
    result=compare(data,'base','candidate',draws=100)
    assert result['masks']['ready']['n']==4
    assert result['masks']['ready']['candidate_correct']==3
    assert result['masks']['ready']['baseline_correct']==1


@pytest.mark.parametrize('problem',['duplicate','nonfinite','missing_arm'])
def test_invalid_comparisons_fail(problem):
    data=sample()
    if problem=='duplicate':
        data=pd.concat([data,data.iloc[:1]],ignore_index=True)
    elif problem=='nonfinite':
        data.loc[0,'prediction']=np.nan
    else:
        data=data[data.arm=='base']
    with pytest.raises(ValueError):
        compare(data,'base','candidate',draws=100)
