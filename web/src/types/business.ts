export interface Review {
  text: string
  author: string
  rating: number
}

export interface ReviewIntel {
  /** Frequently-mentioned quality phrases extracted from real reviews */
  top_highlights: string[]
  /** Specific menu / product items mentioned by customers */
  signature_items: string[]
  /** Atmosphere and vibe descriptors drawn from review text */
  experience_tags: string[]
  /** Best single review quote, max 120 chars */
  top_review_quote: string
}

export interface BusinessData {
  // Identity
  name: string
  city: string
  address: string
  phone: string
  website: string
  category: string
  // Scores
  rating: number
  reviews_count: number
  // Links
  google_maps_url: string
  place_id: string
  // Images — real first, Unsplash fallback
  hero_image: string
  gallery_images: string[]
  has_real_photos: boolean
  // Reviews — real only
  reviews: Review[]
  has_real_reviews: boolean
  // Map
  map_embed: string
  // Synthesised fallback copy (used only when review_intel is empty)
  tagline: string
  services: string[]
  industry: string
  // Review intelligence — frequency-extracted, no fabrication
  // Optional for backwards compatibility with older demo JSONs
  review_intel?: ReviewIntel
}
