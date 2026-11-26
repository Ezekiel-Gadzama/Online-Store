import { MARKETPLACE_OPTIONS, type MarketplaceConnection } from '../api/marketplaceConnections'

function labelForSlug(slug: string, connections: MarketplaceConnection[]): string {
  const conn = connections.find((c) => c.marketplace.toLowerCase() === slug.toLowerCase())
  if (conn?.label?.trim()) return conn.label.trim()
  return MARKETPLACE_OPTIONS.find((o) => o.id === slug)?.label ?? slug
}

/** Center header subtitle from enabled APIs and current marketplace filter. */
export function marketplaceHeaderLine(
  connections: MarketplaceConnection[],
  selectedSlugs: string[],
): string {
  const enabled = connections.filter((c) => c.is_enabled)
  if (!enabled.length) {
    return 'All marketplaces'
  }
  const enabledSlugs = enabled.map((c) => c.marketplace.toLowerCase())
  const selected = (selectedSlugs.length ? selectedSlugs : enabledSlugs).map((s) => s.toLowerCase())
  const slugs =
    selected.length >= enabledSlugs.length && enabledSlugs.every((s) => selected.includes(s))
      ? enabledSlugs
      : selected.filter((s) => enabledSlugs.includes(s))
  if (!slugs.length) {
    return enabled.map((c) => labelForSlug(c.marketplace, connections)).join(', ')
  }
  return slugs.map((s) => labelForSlug(s, connections)).join(', ')
}