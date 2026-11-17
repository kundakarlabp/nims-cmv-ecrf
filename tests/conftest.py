"""Set disposable test process configuration before importing the application."""
import os
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/nims_cmv_ecrf_staging_tests.sqlite3')
os.environ['COOKIE_SECURE']='false'
