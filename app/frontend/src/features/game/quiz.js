/**
 * Lesson steps built only from real content: each word's recorded example (GET /reference/{sign})
 * and its name. The app cannot grade a signed answer yet, so every quiz is about recognising a
 * shown example, never about the learner's own signing.
 */
import { LESSONS } from './progress'

/** Short tips shown with learn steps: general sign-language facts or practical SignLine advice. */
export const TIPS = [
  { kind: 'How signs work', text: 'Watch three things: the hand shape, where the hands are, and how they move. Changing any of them can change the word.' },
  { kind: 'Did you know', text: 'Indian Sign Language is a language of its own, with its own grammar. It is not Hindi or English spelled out with the hands.' },
  { kind: 'Did you know', text: 'In sign languages the face carries meaning too: for example, raised or lowered eyebrows can mark a question.' },
  { kind: 'Practice tip', text: 'The examples are mirrored like your camera: copy them as if you were looking in a mirror.' },
  { kind: 'Practice tip', text: 'Signs can differ between regions and signers. If you sign a word differently, teach SignLine your version on the Customize your sign page.' },
  { kind: 'Did you know', text: 'The Indian Sign Language Research and Training Centre (ISLRTC) publishes an official ISL dictionary on islrtc.nic.in.' },
  { kind: 'Practice tip', text: 'On the Communication page, hold your hands still for a moment after each sign so SignLine can tell where it ends.' },
]

/** Small seeded random generator so a lesson's step order is stable while it is open. */
export function rng(seed) {
  let x = seed >>> 0 || 1
  return () => {
    x ^= x << 13; x >>>= 0; x ^= x >> 17; x ^= x << 5; x >>>= 0
    return x / 4294967296
  }
}

function shuffle(arr, rand) {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function distractors(word, pool, n, rand) {
  return shuffle(pool.filter((w) => w !== word), rand).slice(0, n)
}

/**
 * @param lesson   entry of LESSONS
 * @param usable   (sign) => boolean: has a recorded example (from /labels); unknown → true
 * @param learned  words already learned in earlier lessons (for review steps)
 * @param seed     number
 * @returns steps: {type:'learn', word, tip} | {type:'name', word, options} | {type:'truefalse', word, claim}
 */
export function buildLessonSteps(lesson, usable, learned = [], seed = 1) {
  const rand = rng(seed)
  const words = lesson.words.filter(usable)
  const unitPool = LESSONS.filter((l) => l.unitId === lesson.unitId).flatMap((l) => l.words).filter(usable)
  const widePool = LESSONS.filter((l) => l.track === lesson.track).flatMap((l) => l.words).filter(usable) // letters with letters, phrases with phrases
  const poolFor = (w) => (unitPool.length >= 4 ? unitPool : widePool).filter((x) => x !== w)
  const tipStart = Math.floor(rand() * TIPS.length)

  const learnSteps = words.map((word, i) => ({ type: 'learn', word, tip: TIPS[(tipStart + i) % TIPS.length] }))
  const quiz = words.map((word, i) => {
    if (i % 2 === 0 || words.length < 2) {
      return { type: 'name', word, options: shuffle([word, ...distractors(word, poolFor(word), 3, rand)], rand) }
    }
    const truth = rand() < 0.5
    return { type: 'truefalse', word, claim: truth ? word : distractors(word, poolFor(word), 1, rand)[0] }
  })
  const reviews = shuffle(learned.filter((w) => usable(w) && !words.includes(w)), rand).slice(0, 2)
    .map((word) => ({ type: 'name', word, review: true, options: shuffle([word, ...distractors(word, widePool, 3, rand)], rand) }))
  return [...learnSteps, ...shuffle([...quiz, ...reviews], rand)]
}

export function isCorrect(step, answer) {
  if (step.type === 'name') return answer === step.word
  if (step.type === 'truefalse') return answer === (step.claim === step.word)
  return true
}
