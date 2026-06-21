from scripts.doctor import main


def test_doctor_runs():
    assert main([]) == 0
