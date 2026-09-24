import { test } from 'node:test'
import assert from 'node:assert/strict'
import { videoState } from '../src/lib/videoState.ts'

const completed = { status: 'COMPLETED', vertical_url: '/api/studio/stream/final.mp4' }
test('finished Studio video does not require optional upscale', () => {
  assert.equal(videoState(completed, []), 'COMPLETED')
})
test('an actual active request takes precedence over an old result', () => {
  assert.equal(videoState(completed, [{status:'PROCESSING'}]), 'RUNNING')
  assert.equal(videoState(completed, [{status:'PENDING'}]), 'QUEUED')
})
test('old failed videos are not described as queued', () => {
  assert.equal(videoState({status:'DRAFT'}, [{status:'FAILED',id:'r',type:'GENERATE_VIDEO'}]), 'FAILED')
  assert.equal(videoState({status:'DRAFT'}, []), 'IDLE')
})
test('successful retry supersedes prior failed generation', () => {
  const common = {scene_id:'s',orientation:'VERTICAL'}
  assert.equal(videoState({status:'DRAFT'}, [
    {...common,id:'1',type:'GENERATE_VIDEO',status:'FAILED',created_at:'2026-01-01'},
    {...common,id:'2',type:'REGENERATE_VIDEO',status:'COMPLETED',created_at:'2026-01-02'},
  ]), 'IDLE')
})
