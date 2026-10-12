"""Tabular cloud and database adapters feeding the existing immutable snapshot worker."""
import csv,io,json
from pathlib import Path
from typing import Literal,Optional,Any
from urllib.parse import quote
import httpx
from pydantic import BaseModel,Field
from . import datasets,decks,data_links
from .errors import CiceroError
from .hoard_link.ids import new_ulid
from .util import jdump

class ConnectorArgs(BaseModel):
    deck_id:str
    kind:Literal['sheet','database']
    title:str=''
    spreadsheet_id:str=''
    range:str='Sheet1'
    gid:str='0'
    api_key:str=''
    bearer_token_file:str=''
    database_url:str=''
    query:str=''
    parameters:dict[str,Any]=Field(default_factory=dict)
    interval_s:float=Field(60,gt=0,allow_inf_nan=False)
    number_format:datasets.NumberFormat='auto'

def table_csv(rows):
    out=io.StringIO(newline='');csv.writer(out).writerows(rows);return out.getvalue().encode('utf-8')

def read(svc,deck_id,definition):
    adapter=definition['adapter'];kind=adapter['kind']
    if kind=='sheet':
        sid=adapter['spreadsheet_id']
        if not sid or '/' in sid:raise CiceroError('Supply a native spreadsheet ID')
        headers={};token_file=adapter.get('bearer_token_file')
        if token_file:
            raw=Path(token_file).expanduser().read_text(encoding='utf-8').strip()
            token=json.loads(raw).get('access_token','') if raw.startswith('{') else raw
            headers['Authorization']='Bearer '+token
        with httpx.Client(timeout=30,follow_redirects=True) as client:
            if headers or adapter.get('api_key'):
                url='https://sheets.googleapis.com/v4/spreadsheets/'+sid+'/values/'+quote(adapter.get('range') or 'Sheet1',safe='')
                response=client.get(url,params={'key':adapter.get('api_key') or None,'valueRenderOption':'UNFORMATTED_VALUE'},headers=headers)
                response.raise_for_status();data=table_csv(response.json().get('values',[]))
            else:
                url='https://docs.google.com/spreadsheets/d/'+sid+'/export'
                response=client.get(url,params={'format':'csv','gid':adapter.get('gid','0'),'range':adapter.get('range') or None})
                response.raise_for_status();data=response.content
        origin={'connector':'sheet','spreadsheet_id':sid,'range':adapter.get('range')}
    else:
        from sqlalchemy import create_engine,text
        from sqlalchemy.engine import make_url
        import sqlglot
        from sqlglot import expressions as exp
        tree=sqlglot.parse(adapter['query'])
        if len(tree)!=1 or any(isinstance(n,(exp.Insert,exp.Update,exp.Delete,exp.Drop,exp.Create,exp.Alter,exp.Command)) for n in tree[0].walk()):
            raise CiceroError('Dataset queries must read data, not modify the database')
        if not isinstance(tree[0],(exp.Select,exp.Union)):raise CiceroError('Supply a SELECT dataset query')
        engine=create_engine(adapter['database_url'])
        try:
            with engine.connect() as connection:
                if engine.dialect.name=='sqlite':connection.exec_driver_sql('PRAGMA query_only=ON')
                elif engine.dialect.name in ('postgresql','mysql'):connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                result=connection.execute(text(adapter['query']),adapter.get('parameters') or {})
                data=table_csv([list(result.keys()),*[list(row) for row in result]])
        finally:engine.dispose()
        origin={'connector':'database','url':make_url(adapter['database_url']).render_as_string(hide_password=True),'query':adapter['query']}
    return datasets.import_data(svc,datasets.ImportArgs(deck_id=deck_id,title=definition.get('title',''),number_format=definition.get('number_format','auto')),
                                data,'connector.csv',origin)

def create(svc,args):
    decks._deck_row(svc,args.deck_id)
    if args.kind=='database' and not args.database_url:raise CiceroError('Supply database_url and query')
    definition={'title':args.title,'number_format':args.number_format,'adapter':args.model_dump(exclude={'deck_id','title','interval_s','number_format'})}
    link_id=new_ulid()
    svc.db.execute('INSERT INTO data_links(id,deck_id,definition,enabled,interval_s) VALUES(?,?,?,?,?)',
                   (link_id,args.deck_id,jdump(definition),True,args.interval_s))
    try:return {**data_links.refresh(svc,args.deck_id,link_id),'kind':args.kind}
    except Exception:
        svc.db.execute('UPDATE data_links SET enabled=0 WHERE id=?',(link_id,));raise
