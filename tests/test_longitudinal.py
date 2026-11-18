"""Protocol exposure records: dates, formulations, allocation and blindness."""
from datetime import date
import pytest
from app.main import app  # Initialize application routers before direct helpers.
from app.crf_schema import validate_payload


def test_longitudinal_medication_retains_dose_and_formulation():
    data = dict(start_on='2026-10-01', drug='mycophenolate_sodium',
                indication='maintenance', record_type='prescribed',
                dose_per_administration=360, dose_unit='mg', frequency='twice_daily',
                route='oral', source_reference='TEST-SIGNED-RX')
    assert validate_payload('M_medication', data) == data
    with pytest.raises(ValueError, match='End date'):
        validate_payload('M_medication', dict(data, end_on='2026-09-30'))
    with pytest.raises(ValueError, match='dose'):
        validate_payload('M_medication', dict(data, dose_per_administration=0))


def test_lab_units_and_missing_results_are_not_assumed():
    data = dict(sample_on='2026-10-02', context='vgcv_initiation',
                creatinine_mg_dl=1.4, anc_per_ul=2500,
                source_reference='TEST-LAB-002')
    result = validate_payload('N_laboratory', data)
    assert result == data and 'platelets_per_ul' not in result
    with pytest.raises(ValueError, match='ANC'):
        validate_payload('N_laboratory', dict(data, wbc_per_ul=2000))


def test_infection_episode_does_not_infer_confirmed_diagnosis():
    data = dict(onset_on='2026-10-03', syndrome='urinary_tract',
                certainty='suspected', infection_category='bacterial',
                source_reference='TEST-NOTE-003')
    result = validate_payload('O_infection', data)
    assert result['certainty'] == 'suspected' and 'organism' not in result
    with pytest.raises(ValueError, match='End date'):
        validate_payload('O_infection', dict(data, resolved_on='2026-10-02'))


def test_pretransplant_medication_allowed_but_infection_after_transplant_required():
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.trial_crf import enforce_record_date
    subject = SimpleNamespace(pcr_anchor_on=date(2026, 10, 1))
    enforce_record_date(subject, date(2026, 9, 30), 'M_medication')
    with pytest.raises(HTTPException):
        enforce_record_date(subject, date(2026, 9, 30), 'O_infection')
