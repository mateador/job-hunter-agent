from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def no_real_company_research():
    """Tests must never hit DuckDuckGo. Tests that exercise research patch it themselves."""
    with patch("src.job_agent.agent_runner.research_company", return_value=None):
        yield
