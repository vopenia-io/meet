import { describe, expect, it } from 'vitest'
import { parseMoveMe } from './commands'

describe('parseMoveMe', () => {
  it('reads the region asked for', () => {
    expect(parseMoveMe('/moveme de')).toEqual({ region: 'de' })
    expect(parseMoveMe('  /MoveMe   gra9  ')).toEqual({ region: 'gra9' })
  })

  it('takes no region for the region the participant is in', () => {
    expect(parseMoveMe('/moveme')).toEqual({ region: '' })
    expect(parseMoveMe('/moveme   ')).toEqual({ region: '' })
  })

  it('leaves every other message to the chat', () => {
    expect(parseMoveMe('hello')).toBeUndefined()
    expect(parseMoveMe('/movemeplease')).toBeUndefined()
    expect(parseMoveMe('say /moveme de')).toBeUndefined()
    expect(parseMoveMe('/moveme de now')).toBeUndefined()
  })
})
