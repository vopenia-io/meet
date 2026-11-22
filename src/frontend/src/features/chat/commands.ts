/**
 * Commands typed in the chat, which are not sent to the room.
 *
 * `/moveme [region]`: the participant asks the SFU to move it to another
 * node, of `region` if one is named, else of the region it is in. A test
 * command: the backend answers 404 unless `ROOM_MOVE_ME_ENABLED` is set.
 */
export const parseMoveMe = (text: string): { region: string } | undefined => {
  const match = /^\/moveme(?:\s+(\S+))?\s*$/i.exec(text.trim())
  return match ? { region: match[1] ?? '' } : undefined
}
