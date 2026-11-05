"""Assert extraction and persistence preserve every H8 prediction."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from quant.infrastructure.experiment_store import file_hash
from quant.models.native_direction import NativeDirectionLearner

root = Path('artifacts/native-direction-audit')
rows = []
for stage in ['control','replication']:
    old = pd.read_parquet(root/f'binary-logloss-{stage}'/'predictions.parquet')
    new = pd.read_parquet(root/f'binary-logloss-learner-{stage}'/'predictions.parquet')
    keys = ['period','pair','date','arm']
    a, b = old.set_index(keys).sort_index(), new.set_index(keys).sort_index()
    assert a.index.is_unique and a.index.equals(b.index)
    for column in ['truth','prediction','ready','prediction_kind']:
        assert np.array_equal(a[column],b[column]), (stage,column)
    tool = pd.read_parquet(root/f'binary-logloss-tool-{stage}'/'predictions.parquet').set_index(keys).sort_index()
    assert a.index.equals(tool.index)
    for column in ['truth','prediction','ready','prediction_kind']:
        assert np.array_equal(a[column],tool[column]), (stage,'canonical_tool',column)
    audits = json.loads((root/f'binary-logloss-learner-{stage}'/'audit.json').read_text())
    for audit in audits:
        path = root/f'binary-logloss-learner-{stage}'/f"{audit['period']}-{audit['pair'].split('/')[0]}-learner.joblib"
        assert path.is_file()
        directory = next((Path('artifacts/native-prediction-study/runs')/audit['period']/'userdir/models').glob(
            f"*/sub-train-{audit['pair'].split('/')[0]}_*"))
        identity = file_hash(next(directory.glob('*feature_pipeline.pkl')))
        learner = NativeDirectionLearner.load(path, preprocessing_id=identity)
        assert learner.estimator.get_booster().num_boosted_rounds() == audit['candidate_rounds']
    rows.append({'stage':stage,'models':len(audits),'samples_per_arm':len(a)//3,
                 'all_arms_predictions_exactly_equal':True,
                 'canonical_tool_default_config_replay_passed':True,
                 'persisted_contract_load_passed':True,
                 'module_save_load_checked_in_runner':True,'max_prediction_difference':0.0})
(root/'direction-learner-replay.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
