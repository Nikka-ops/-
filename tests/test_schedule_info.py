from scripts.scrape.schedule_info import daily_schedule_status, run_daily_entrypoint


def test_run_daily_entrypoint():
    assert "run_daily_scrape" in run_daily_entrypoint()


def test_daily_schedule_status_shape():
    info = daily_schedule_status()
    assert "platform" in info
    assert "install_hint" in info
    assert "active" in info
    assert "scheduler" in info
