"""Explicit first-party status tags must not become scheduled artist renames."""
import pytest

from scripts.events.sources.html import _YokohamaArenaJson
from scripts.events.types import VenueRecord


@pytest.mark.parametrize('artist,title,status',[
    ('MC TYSON　【公演中止】','BAYSIDE STORY','cancelled'),
    ('出演者','公演 [開催延期]','postponed'),
    ('出演者','公演 【開催中止】','cancelled'),
    ('出演者','公演','scheduled'),
    ('出演者','公演 ※雨天中止の場合があります','scheduled'),
    ('出演者','公演 【一部公演中止】','scheduled'),
])
def test_explicit_status_only_and_raw_performer_preserved(artist,title,status):
    class Response:
        def __init__(self,ok):self.status_code=200 if ok else 404
        def json(self):return [dict(title=title,artist=artist,date1='2026-12-07',date2='2026-12-07',
                                   ev_start=['18:30'],ev_end=[],path='/event/detail/example')]
    class Session:
        calls=0
        def get(self,*args,**kwargs):
            self.calls+=1
            return Response(self.calls==1)
    venue=VenueRecord('yokohama_arena','横浜アリーナ','14','神奈川県',17000,
        'https://www.yokohama-arena.co.jp/','html','https://www.yokohama-arena.co.jp/event/',None,True)
    rows=_YokohamaArenaJson().parse(venue,Session(),{})
    assert len(rows)==1 and rows[0].status==status
    assert rows[0].performers==artist and rows[0].title==title
