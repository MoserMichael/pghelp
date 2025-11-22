

## setup

```python

# first time: create virtual env
python3 -m venv .venv

# venv activate (each usage)
source .venv/bin/activate

# first time: install requirements
pip3 install -r requirements.txt
```

The [psycopg2](https://pypi.org/project/psycopg2/) postgres client is used here.

## configuration

The current directory or home directory must have the file: ```.psqldiff``` for configuring the connect string:


```
[PSQL]

conf=postgresql://<PG_USER>:<PG_PASSWD>>@<PG_HOSTNAME>:<PG_PORT>/<PG_DB>

```

## Comparing the structure of two SQL tables

Shows the difference between the columns declared in two sql statements.

Example: for the following two sql tables

```sql

CREATE TABLE sh1.aaa (
    only_a_1 character varying(10),
    only_a_2 boolean,
    common_1 character varying(10) NOT NULL,
    common_2 character varying(20),
    common_3 integer,
    common_ch_type1 character varying(10)
);

ALTER TABLE ONLY sh1.aaa
    ADD CONSTRAINT aaa_pkey PRIMARY KEY (common_1);


CREATE TABLE sh2.aaa (
    common_1 character varying(10),
    common_2 character varying(20),
    common_3 integer,
    only_b_1 character varying(40),
    only_b_2 integer,
    only_b_3 integer,
    common_ch_type1 character varying(30)
);
```

The following command will compare these two tables

```bash
python psqldiff.py  -f sh1.aaa -t sh2.aaa
```

And give the following result

```
compare tables: sh1.aaa, sh2.aaa
COLUMNS WITH IDENTICAL NAMES AND CHANGED TYPES, OR CONSTRAINTS

column: common_1
        table: sh1.aaa and sh2.aaa of type: character varying(10)
        table: sh1.aaa of constraint: PRIMARY KEY


column: common_ch_type1
        table: sh1.aaa of type: character varying(10)
        table: sh2.aaa of type: character varying(30)


COLUMN NAMES THAT APPEAR IN TABLE sh1.aaa ONLY

        column: only_a_1 with type: character varying(10)
        column: only_a_2 with type: boolean

COLUMN NAMES THAT APPEAR IN TABLE sh2.aaa ONLY

        column: only_b_1 with type: character varying(40)
        column: only_b_2 with type: integer
        column: only_b_3 with type: integer

```

TODO: compare indexes too.

## dump the result of an sql query into a json file

```sql

CREATE TABLE sh1.students(name varchar(10), fav_teacher varchar(20), fav_topic varchar(20));

INSERT INTO sh1.students(name, fav_teacher, fav_topic) 
VALUES 
('Joe A', 'Mr. Larson', 'Physics'), 
('Peggy L', 'Mrs. Brown', 'Mathematics'), 
('Dan L', 'Mrs. Johnson', 'Computers');
```

The following command

```bash

python psql2json.py -q 'SELECT * FROM sh1.students' -f out.json

```

will result in the following json data in file ```out.json```

```json
[
    {
        "name": "Joe A",
        "fav_teacher": "Mr. Larson",
        "fav_topic": "Physics"
    },
    {
        "name": "Peggy L",
        "fav_teacher": "Mrs. Brown",
        "fav_topic": "Mathematics"
    },
    {
        "name": "Dan L",
        "fav_teacher": "Mrs. Johnson",
        "fav_topic": "Computers"
    }
]
```




