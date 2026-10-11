import json
from pathlib import Path
import shutil
import subprocess
import pytest
from cicero_hoard import decks,presentation as live
from cicero_hoard.agent_tools import call_tool
from cicero_hoard.errors import CiceroError,RevisionConflict
from conftest import new_deck

def test_pending_media_play_cannot_resume_after_navigation_or_pause():
 node=shutil.which('node')
 if not node:pytest.skip('Node.js is required to exercise the audience JavaScript runtime.')
 result=subprocess.run([node,str(Path(__file__).with_name('playback_race.cjs')),live.__file__],capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stdout+result.stderr

def talk(svc):
 deck=new_deck(svc)
 first=decks.add_slide(svc,deck['id'],title='First',blocks=[{'type':'text','text':'A','build':2,'effect':'fade'},{'type':'text','text':'B','build':9,'effect':'wipe'}],notes='PRIVATE-NOTES-NOT-AUDIENCE')
 second=decks.add_slide(svc,deck['id'],title='Support',blocks=[{'type':'text','text':'More'}],notes='Other notes')
 return deck,first,second

def test_stages_normalized_navigation_and_support_jump(services):
 deck,_,_=talk(services);room=call_tool(services,'deck_live_start',{'deck_id':deck['id'],'main_slide_count':1})
 assert room['fragment_index']==-1 and room['slides'][0]['steps']==2 and not room['running']
 for expected in (0,1):assert call_tool(services,'deck_live_control',{'deck_id':deck['id'],'action':'next'})['fragment_index']==expected
 result=call_tool(services,'deck_live_control',{'deck_id':deck['id'],'action':'next'})
 assert result['slide_index']==1 and result['fragment_index']==-1
 result=call_tool(services,'deck_live_control',{'deck_id':deck['id'],'action':'previous'})
 assert (result['slide_index'],result['fragment_index'])==(0,1)
 result=call_tool(services,'deck_live_control',{'deck_id':deck['id'],'action':'goto','slide_index':1})
 assert result['slide_index']==1 and result['main_slide_count']==1
 assert 'PRIVATE-NOTES' not in json.dumps(room)

def test_pause_resume_reset_and_target_use_actual_clock(services):
 now=[100.0];services.presentations.clock=lambda:now[0]
 deck,_,_=talk(services);live.start(services,live.StartArgs(deck_id=deck['id'],target_seconds=30))
 control=lambda action,**kw:live.control(services,live.ControlArgs(deck_id=deck['id'],action=action,**kw))
 control('resume');now[0]=112;assert control('pause')['elapsed_seconds']==12
 now[0]=300;assert live.state(services,live.StateArgs(deck_id=deck['id']))['elapsed_seconds']==12
 control('resume');now[0]=325;assert control('pause')['remaining_seconds']==-7
 assert control('target',target_seconds=120)['remaining_seconds']==83
 assert control('reset')['elapsed_seconds']==0

def test_retry_start_and_version_conflicts(services):
 deck,_,_=talk(services);args=live.StartArgs(deck_id=deck['id'])
 first=live.start(services,args);assert live.start(services,args)['session_id']==first['session_id']
 assert live.control(services,live.ControlArgs(deck_id=deck['id'],action='sync',slide_index=0,fragment_index=-1))['version']==1
 live.control(services,live.ControlArgs(deck_id=deck['id'],action='next',expected_version=1))
 with pytest.raises(RevisionConflict):live.control(services,live.ControlArgs(deck_id=deck['id'],action='next',expected_version=1))
 with pytest.raises(CiceroError):live.control(services,live.ControlArgs(deck_id=deck['id'],action='sync',slide_index=0,fragment_index=3))
 restarted=live.start(services,live.StartArgs(deck_id=deck['id'],restart=True))
 assert restarted['session_id']!=first['session_id'] and restarted['fragment_index']==-1

def test_live_routes_separate_notes_and_reject_changed_session(client):
 deck,first,_=talk(client.svc);base=f"/api/decks/{deck['id']}/live"
 room=client.post(base,json={}).json();path=base+'/'+room['session_id']
 assert room['audience_path']==path+'/audience.html'
 response=client.get(path+'/audience.html')
 assert response.status_code==200 and 'PRIVATE-NOTES' not in response.text
 assert "connect-src 'self'" in response.headers['content-security-policy'] and path+'/speaker' not in response.text
 assert 'PRIVATE-NOTES' not in client.get(path+'/state').text
 assert "deck.on('fragmentshown'" not in response.text and "keyboard:false" in response.text
 assert 'PRIVATE-NOTES' in client.get(path+'/speaker').text
 assert "activate.addEventListener('click'" in response.text
 assert "if(attempt===mediaAttempt)clearMediaNotice()" in response.text
 assert "error.name==='NotAllowedError'" in response.text
 assert "mediaNotice.style.display='block'" in response.text
 assert "pendingMedia&&deck.getCurrentSlide().contains(pendingMedia)" in response.text
 assert "if(previousSlide!==deck.getCurrentSlide())clearMediaNotice()" in response.text
 assert "attempt!==mediaAttempt" in response.text and "error.name==='AbortError'" in response.text
 assert "media.pause();clearMediaNotice()" in response.text
 assert client.post(path+'/control',json={'action':'blackout','blackout':True}).json()['blackout']
 decks.patch_slide(client.svc,deck['id'],first['id'],{'title':'Changed'})
 assert client.get(path+'/state').status_code==409
 current=client.post(base,json={'restart':True}).json()
 assert current['session_id']!=room['session_id'] and client.get(path+'/state').status_code==400

def test_empty_deck_and_invalid_main_count(services):
 deck=new_deck(services)
 with pytest.raises(CiceroError):live.start(services,live.StartArgs(deck_id=deck['id']))
 talk_deck,_,_=talk(services)
 with pytest.raises(CiceroError):live.start(services,live.StartArgs(deck_id=talk_deck['id'],main_slide_count=3))

def test_navigation_poll_does_not_reload_source_text_or_blocks(services,monkeypatch):
 deck,_,_=talk(services);live.start(services,live.StartArgs(deck_id=deck['id']))
 def unnecessary(*_):raise AssertionError('Polling must not materialize the complete deck.')
 monkeypatch.setattr(decks,'deck_view',unnecessary)
 assert live.state(services,live.StateArgs(deck_id=deck['id']))['slide_index']==0
