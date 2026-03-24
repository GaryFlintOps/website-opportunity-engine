export interface Review {
  text: string
  author: string
  rating: number
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
  // Synthesised
  tagline: string
  services: string[]
  industry: string
}
