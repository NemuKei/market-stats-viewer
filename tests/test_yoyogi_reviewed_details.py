"""Optional venue-detail collection stays private until an explicit data review."""
from types import SimpleNamespace

import pytest

from scripts.events.sources.html import _YoyogiGymnasiumSchedule

BASE='https://www.jpnsport.go.jp/yoyogi/event/tabid/59/Default.aspx'
URL='https://www.jpnsport.go.jp/yoyogi/Default.aspx?TabId=59&eid=6172&etype='
TITLE='NMIXX JAPAN DEBUT SHOWCASE'

def detail(clock='17:30',day='2026/11/08',title=TITLE,facility='第一体育館'):
    return f'''<h1>イベント情報（{facility}）</h1><table class="event-calendar">
    <tr><th>日程</th><td>{day}</td></tr><tr><th>イベント名</th><td>{title}</td></tr>
    <tr><th>開場時間</th><td>16:30</td></tr><tr><th>開始時間</th><td>{clock}</td></tr></table>'''

class Session:
    def __init__(self,types=('1','2'),body=None):
        self.types,self.body,self.calls=types,body or detail(),[]
    def get(self,url,**kw):
        self.calls.append(url)
        if url==BASE:
            text='<table class="event-calendar">'+''.join(f'<tr><td>2026/11/08(日)</td><td><a href="{URL+t}">{TITLE}</a></td></tr>' for t in self.types)+'</table>'
        else:
            text=self.body
        return SimpleNamespace(url=url,status_code=200,text=text,encoding='utf-8',apparent_encoding='utf-8',raise_for_status=lambda:None)

def parse(session,**config):
    venue=SimpleNamespace(venue_id='yoyogi_gymnasium',source_url=BASE,source_type='html')
    return _YoyogiGymnasiumSchedule().parse(venue,session,config)

def test_default_retains_legacy_shape_and_never_fetches_details():
    session=Session()
    rows=parse(session)
    assert len(rows)==2 and all(r.start_time is None and r.all_day for r in rows)
    assert session.calls==[BASE]

def test_reviewed_opt_in_reads_start_not_doors_and_uses_native_event_identity():
    session=Session()
    a=parse(session,fetch_details=True,publication_review=True)
    b=parse(Session(types=('2',)),fetch_details=True,publication_review=True)
    assert len(a)==len(b)==1
    assert a[0].start_time=='17:30' and not a[0].all_day
    assert a[0].event_uid==b[0].event_uid and a[0].source_event_key=='eid:6172#date:2026-11-08'
    assert a[0].source_url==BASE and a[0].url==URL+'1'
    assert session.calls==[BASE,URL+'1',URL+'2']

@pytest.mark.parametrize('body',[detail(day='2026/11/09'),detail(title='Other'),detail(facility='第二体育館'),detail(clock='13:00 / 17:00')])
def test_mismatched_or_multiple_start_details_require_review(body):
    with pytest.raises(ValueError):
        parse(Session(body=body),fetch_details=True,publication_review=True)

def test_blank_start_stays_unknown_and_opt_in_requires_private_publication_gate():
    rows=parse(Session(body=detail(clock='')),fetch_details=True,publication_review=True)
    assert rows[0].start_time is None and rows[0].all_day
    with pytest.raises(ValueError):
        parse(Session(),fetch_details=True)


def test_same_native_event_with_conflicting_titles_is_not_silently_collapsed():
    session=Session()
    get=session.get
    def conflicting(url,**kw):
        response=get(url,**kw)
        if url==BASE:
            response.text=response.text.replace(f'{URL}2">{TITLE}',f'{URL}2">Different evening show')
        return response
    session.get=conflicting
    with pytest.raises(ValueError,match='conflicting|differs'):
        parse(session,fetch_details=True,publication_review=True)


@pytest.mark.parametrize('label,value',[('開始時間','13:00'),('日程','2026/11/08'),('イベント名',TITLE)])
def test_duplicate_detail_fact_labels_are_not_overwritten(label,value):
    body=detail().replace('</table>',f'<tr><th>{label}</th><td>{value}</td></tr></table>')
    with pytest.raises(ValueError,match='duplicate'):
        parse(Session(body=body),fetch_details=True,publication_review=True)


def test_two_observed_urls_for_one_native_event_must_agree_on_start():
    session=Session()
    get=session.get
    def alternate(url,**kw):
        response=get(url,**kw)
        if url==URL+'2':
            response.text=detail(clock='13:00')
        return response
    session.get=alternate
    with pytest.raises(ValueError,match='conflicting'):
        parse(session,fetch_details=True,publication_review=True)


def test_same_native_id_does_not_skip_validation_of_another_detail_url():
    session=Session()
    get=session.get
    def malicious(url,**kw):
        response=get(url,**kw)
        if url==BASE:
            response.text=response.text.replace(URL+'2','https://unreviewed.example/yoyogi/Default.aspx?TabId=59&eid=6172&etype=2')
        return response
    session.get=malicious
    with pytest.raises(ValueError,match='URL'):
        parse(session,fetch_details=True,publication_review=True)
    assert not any('unreviewed.example' in url for url in session.calls)


@pytest.mark.parametrize('stage',['calendar','detail'])
def test_opt_in_refuses_redirected_acquisition_or_detail(stage):
    session=Session(types=('1',))
    get=session.get
    def redirect(url,**kw):
        response=get(url,**kw)
        if (url==BASE)==(stage=='calendar'):
            response.url='https://unreviewed.example/calendar'
        return response
    session.get=redirect
    with pytest.raises(ValueError,match='redirect'):
        parse(session,fetch_details=True,publication_review=True)
