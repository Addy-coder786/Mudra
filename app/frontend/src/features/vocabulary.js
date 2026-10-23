import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../services/signRecognizer'
import { readableSign } from '../services/islDictionary'
import { fetchLibrary } from '../services/libraryClient'

/**
 * The model's vocabulary from GET /labels (word, readable label, whether a recorded example exists,
 * held-out test results), plus the library from GET /library (fingerspelling letters LETTER_A..Z and
 * phrases) in `extra`. Fetched once per page load and shared.
 */
let cache = null

// How the app states its vocabulary size wherever a word count is shown (owner's wording, 2026-10-24)
export const VOCABULARY_SIZE = '500+'

export function fetchVocabulary() {
  if (!cache) {
    cache = fetch(`${API_BASE_URL}/labels`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(async (body) => {
        const lib = await fetchLibrary()
        const extra = Object.fromEntries([
          ...lib.letters.map((l) => [l.sign, { ...l, kind: 'letter' }]),
          ...lib.phrases.map((l) => [l.sign, { ...l, kind: 'phrase' }]),
        ])
        return { status: 'online', labels: Object.fromEntries((body.labels || []).map((l) => [l.sign, l])), extra }
      })
      .catch(() => {
        cache = null // retry on the next call
        return { status: 'offline', labels: {}, extra: {} }
      })
  }
  return cache
}

export function useVocabulary() {
  const [vocab, setVocab] = useState({ status: 'loading', labels: {}, extra: {} })
  useEffect(() => {
    let alive = true
    fetchVocabulary().then((v) => alive && setVocab(v))
    return () => { alive = false }
  }, [])
  const entry = (sign) => vocab.labels[sign] || vocab.extra?.[sign]
  const label = (sign) => entry(sign)?.label || readableSign(sign)
  const hasExample = (sign) => (vocab.status === 'online' ? Boolean(entry(sign)?.has_reference) : true)
  return { ...vocab, label, hasExample, entry }
}
