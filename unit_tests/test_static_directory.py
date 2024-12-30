from robyn import Robyn, SubRouter


def test_static_directory():
    app = Robyn(__file__)
    app.set_static_files_directory()


def test_subroute_static_directory():
    app = Robyn(__file__)
    subroute = SubRouter(__name__, prefix="/test-subroute")
    app.include_router(subroute)
    subroute.set_static_files_directory()
