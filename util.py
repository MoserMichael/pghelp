from pathlib import Path
import sys 
import configparser
import psycopg2
from psycopg2.extras import RealDictCursor

def err(msg):
    print(f"Error: {msg}")
    sys.exit(1)

def find_conf(filename):
    current_dir = Path.cwd()
    file_path_current = current_dir / filename
    if file_path_current.exists():
        return file_path_current

    # Search in home directory
    home_dir = Path.home()
    file_path_home = home_dir / filename
    if file_path_home.exists():
        return file_path_home

    err(f"'{filename}' not found in current or home directory.")

def read_value(config, fpath, section, option):    
    if not config.has_section(section):
        err(f"Not section {section} in {fpath}]")
    if not config.has_option(section, option):
        err(f"Not {option} value in section {section} in {fpath}]")
    return config[section][option]


def read_conf():
    cfg_file = ".psqldiff"
    fpath = find_conf(cfg_file)
    config = configparser.ConfigParser()

    # Read the configuration file
    try:
        config.read(fpath)
        return read_value(config, fpath, 'PSQL', 'conf')
    except Exception as ex:
        err(f"Can't read configuration file {fpath} error: {ex}")

    err("wtf error")    

def db_connect(conn_str, read_only=True):
    #print(f"->connecting {conn_str}")
    conn = psycopg2.connect(conn_str, cursor_factory=RealDictCursor)
    conn.set_session(readonly=read_only, autocommit=True)
    return conn


def run_sql(conn, stmt):
    try:
        with conn.cursor() as cursor:
            
            cursor.execute(stmt)
            rows = cursor.fetchall()

            ret_rows = []
            for row in rows:
                ret_row = {}
                
                for column in row.items():
                    ret_row[column[0]] = column[1]

                ret_rows.append(ret_row)
            return ret_rows
    except Exception as e:
        err(f"failed to run query {stmt}, error: {e}")
