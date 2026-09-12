from rhapto.services.naming import download_basename


def test_download_basename_normalises_and_falls_back() -> None:
    assert download_basename("Maya Chen") == "Maya_Chen"
    assert download_basename("  Ana-María O'Neil  ") == "Ana_Mar_a_O_Neil"
    assert download_basename("") == "Resume"
    assert download_basename(None) == "Resume"
    assert download_basename("___") == "Resume"
