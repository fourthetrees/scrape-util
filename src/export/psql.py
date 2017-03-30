#!/usr/bin/env python3
from src.core.errlog import errdata,mklog
import psycopg2 as psql
import time


# Main push-to-psql entry point
def export(data,project,config):
    db  = config['general']['database']
    tbl = config['general']['table']
    fields = data[0]._fields
    # handle custom-inserion instance if needed.
    if 'conversions' in config:
        ins = custom_insertion(fields,config['conversions'])
    # default is just standard psycopg2 formatting...
    else: ins = ','.join(['%s'] * len(fields))
    cmd = 'INSERT INTO {} VALUES ({})'.format(tbl,ins)
    errs,errtxt,dupcount = exec_push(data,cmd,db)
    if dupcount:
        print('duplicate rows ignored: ',dupcount)
    # save any rows which raised unexpexted errors
    # to a csv with prefix `psqlerr`.
    if errs: errdata(project,data,txt='psqlerr')
    # append any unexpected errors to
    # the project's main error log.
    for err in errtxt: mklog(project,err)

def exec_push(data,cmd,db):
    errs,errtxt = [],[]
    duplicates = 0
    errcount = 0
    with psql.connect(database=db) as con:
        con.set_session(autocommit=True)
        for i in range(len(data)):
            row = data.pop(0)
            try:
                with con.cursor() as cur:
                    cur.execute(cmd,row)
            except Exception as err:
                if 'duplicate key' in str(err):
                    dupcount += 1
                    break
                else:
                    errs.append(row)
                    errtxt.append(err)
                    errcount += 1
                    if errcount > 10:
                        errs += data
                        errtxt.append("stopping upload attempts")
                        data = []
                        break
    if data:
        e,t,d = exec_push(data,cmd,db)
        errs += e
        errtxt += t
        duplicates += d
    return errs,errtxt,duplicates


# Actually push the stuff
def exec_push_old(data,cmd,db):
    errs,errtxt = [],[]
    dupcount = 0
    print('pushing {} rows to database: {}'.format(len(data),db))
    with psql.connect(database=db) as con:
        # activate autocommit so duplicate rows
        # don't kill the entire uplaod proecess.
        con.set_session(autocommit=True)
        for index,row in enumerate(data):
            try:
                # cursor context manager handles cursor
                # related cleanup on exception; kinda slow to
                # use an individual cursor for each row, but
                # necessary when duplicate data is an issue.
                with con.cursor() as cur:
                    cur.execute(cmd,row)
            except Exception as err:
                # duplicate key errors are ignored to facilitate recovery
                # from partial uplaod, loss of nonce file, etc...
                if 'duplicate key' in str(err):
                    dupcount += 1
                    data = data[index-1:]


                else:
                    errs.append(row)
                    errtxt.append(err)
    con.close()
    return errs,errtxt,dupcount



# Generate a custom insertion string.
def custom_insertion(fields,insmap):
    # collection of all possible insertion strings.
    inserts = {
        'default' : '%s',
        'to-timestamp' : 'to_timestamp(%s)'
    }
    for i in insmap:
        if i not in fields:
            raise Exception('unrecognized data field: {}'.format(i))
        if insmap[i] not in inserts:
            raise Exception('unrecognized insertion type: {}'.format(insmap[i]))
    ins = []
    # build the custom insertion string field by field.
    for f in fields:
        if f in insmap:
            ins.append(inserts[insmap[f]])
        else: ins.append(inserts['default'])
    return ','.join(ins)
