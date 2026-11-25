import pytest

from archive.fe110_grouped_submission_20261025.submit import check_account


def test_account_limit_uses_named_column_not_run_count():
    assert check_account("USER/GROUP JL/P MAX NJOBS PEND RUN\nuser 3 128 10 6 128\n") == 128


@pytest.mark.parametrize("table", ["", "unparseable", "USER MAX\nuser 64\n"])
def test_unknown_or_changed_limit_cannot_authorize_submission(table):
    with pytest.raises(ValueError):
        check_account(table)
