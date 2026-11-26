export function userDisplayName(user: { name?: string | null; email: string } | null | undefined): string {
  if (!user) return ''
  const n = user.name?.trim()
  if (n) return n
  return user.email
}

export function assigneeDisplayName(u: { name?: string | null; email: string }): string {
  const n = u.name?.trim()
  if (n) return n
  return u.email
}