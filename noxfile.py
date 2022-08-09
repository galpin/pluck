from nox_poetry import session

versions = ['3.9', '3.10']


@session(python=versions)
def tests_json(session):
    pytest(session)


@session(python=versions)
def tests_orjson(session):
    session.install('orjson')
    pytest(session)


def pytest(session):
    session.run('pytest')
