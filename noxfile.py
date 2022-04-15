import nox

versions = ['3.9', '3.9', '3.10']


@nox.session(python=versions)
def tests_json(session):
    install_requirements(session)
    pytest(session)


@nox.session(python=versions)
def tests_orjson(session):
    install_requirements(session)
    session.install('orjson')
    pytest(session)


def pytest(session):
    session.run('pytest')


def install_requirements(session):
    session.install('-r', 'requirements.txt')
