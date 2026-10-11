import io
import zipfile
from lxml import etree
from cicero_hoard.export_pptx import build_pptx
from cicero_hoard.chart_cache import refresh_numeric_caches

def test_native_decimal_cache_is_refreshed_without_changing_workbook():
    deck={'title':'Evidence','language':'en','theme':'claro','slides':[{'id':'s','position':1,'layout':'evidence','title':'Numeric evidence',
        'blocks':[{'type':'chart','chart':'line','categories':['2','30'],'series':[{'name':'Observed','values':[1.72,2.01],'x_values':[2,30]}]}]}]}
    raw=build_pptx(deck,assets=lambda _:None)
    altered=io.BytesIO();chart='ppt/charts/chart1.xml'
    with zipfile.ZipFile(io.BytesIO(raw)) as z,zipfile.ZipFile(altered,'w') as out:
        for info in z.infolist():
            data=z.read(info.filename)
            if info.filename==chart:data=data.replace(b'<c:v>2.01</c:v>',b'<c:v>2.0099999999999998</c:v>')
            out.writestr(info,data)
    fixed,report=refresh_numeric_caches(altered.getvalue())
    assert report['updated_points']==1 and not report['unresolved']
    with zipfile.ZipFile(io.BytesIO(raw)) as before,zipfile.ZipFile(io.BytesIO(fixed)) as after:
        for name in before.namelist():
            if name!=chart:assert before.read(name)==after.read(name)
        xml=etree.fromstring(after.read(chart));ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
        assert xml.findall('.//c:yVal//c:pt/c:v',ns)[1].text=='2.01'
    again,report=refresh_numeric_caches(fixed)
    assert again==fixed and report['updated_points']==0
