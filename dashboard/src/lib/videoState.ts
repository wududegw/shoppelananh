import type { Request, Video } from '../types'

export function videoState(video: Video, requests: Request[]): 'COMPLETED' | 'RUNNING' | 'QUEUED' | 'FAILED' | 'IDLE' {
  if (requests.some(r => r.status === 'PROCESSING')) return 'RUNNING'
  if (requests.some(r => r.status === 'PENDING')) return 'QUEUED'
  if (video.status === 'COMPLETED' && (video.vertical_url || video.horizontal_url)) return 'COMPLETED'
  const latest = new Map<string, Request>()
  for (const r of requests) {
    const key = `${r.scene_id || r.character_id || r.id}:${r.type.replace('REGENERATE', 'GENERATE')}:${r.orientation}`
    const prior = latest.get(key)
    if (!prior || r.created_at > prior.created_at || (r.created_at === prior.created_at && r.updated_at > prior.updated_at)) latest.set(key, r)
  }
  if ([...latest.values()].some(r => r.status === 'FAILED') || video.status === 'FAILED') return 'FAILED'
  return 'IDLE'
}
