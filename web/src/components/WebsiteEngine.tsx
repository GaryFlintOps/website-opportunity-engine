import type { BusinessData, Review, ReviewIntel } from '@/types/business'

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderStars(rating: number): string {
  const full  = Math.floor(rating)
  const half  = rating - full >= 0.3 ? 1 : 0
  const empty = 5 - full - half
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty)
}

function hasIntelContent(ri: ReviewIntel | undefined): boolean {
  if (!ri) return false
  return ri.top_highlights.length > 0 || ri.signature_items.length > 0 || ri.experience_tags.length > 0
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function WebsiteEngine({ data }: { data: BusinessData }) {
  const {
    name, address, phone,
    rating, reviews_count, google_maps_url,
    hero_image, gallery_images,
    has_real_photos,
    reviews, map_embed, services,
    review_intel,
  } = data

  const stars = rating ? renderStars(rating) : ''

  // WhatsApp deep-link — strip all non-digits from phone
  const waPhone = (phone || '').replace(/\D/g, '')
  const waMsg   = encodeURIComponent(
    `Hi ${name} — I built a website preview for you using your Google reviews. Can I show you how this could bring you more customers?`
  )
  const waLink  = waPhone ? `https://wa.me/${waPhone}?text=${waMsg}` : '#contact'

  // Hero quote — prefer extracted intel quote, fall back to first good review
  const heroQuote: string = review_intel?.top_review_quote ||
    (() => {
      const r = reviews.find((r: Review) => r.rating === 5 && r.text.length > 30) || reviews[0]
      if (!r) return ''
      const t = r.text.replace(/\s+/g, ' ').trim()
      return t.length <= 120 ? t : t.slice(0, 120).rsplit?.(' ', 1)?.[0] + '…' || t.slice(0, 120) + '…'
    })()

  // Gallery — max 10, consistent
  const gallerySlice = gallery_images.slice(0, 10)

  // Does review intel have enough to replace the services section?
  const useReviewIntel = hasIntelContent(review_intel)

  return (
    <>
      {/* ── Design system — self-contained inline CSS ── */}
      <style>{`
        /* Reset */
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        /* Base */
        body {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          color: #111827;
          background: #fff;
          line-height: 1.6;
          -webkit-font-smoothing: antialiased;
        }

        /* ── Typography scale ── */
        /* Hero:    clamp(2.25rem, 5vw, 3rem) / 600  */
        /* Section: clamp(1.5rem, 3vw, 1.875rem) / 600 */
        /* Body:    1rem / 400 / gray-600 (#4b5563) */
        /* Small:   0.875rem / 400 / gray-400 (#9ca3af) */

        /* ── NAV ── */
        .we-nav {
          position: fixed; top: 0; left: 0; right: 0; z-index: 100;
          display: flex; align-items: center; justify-content: space-between;
          padding: 1.1rem 1.5rem;
          background: rgba(255,255,255,0.96);
          backdrop-filter: blur(8px);
          border-bottom: 1px solid #f3f4f6;
          max-width: 100%;
        }
        .we-nav-inner {
          width: 100%; max-width: 72rem; margin: 0 auto;
          display: flex; align-items: center; justify-content: space-between;
        }
        .we-nav-logo {
          font-size: 1rem; font-weight: 600; color: #111827;
          letter-spacing: -0.01em;
        }
        .we-nav-cta {
          background: #16a34a; color: #fff;
          text-decoration: none; padding: 0.55rem 1.25rem;
          border-radius: 6px; font-size: 0.875rem; font-weight: 600;
          transition: background 0.2s;
        }
        .we-nav-cta:hover { background: #15803d; }

        /* ── HERO ── */
        .we-hero {
          position: relative; min-height: 100vh;
          display: flex; align-items: center; justify-content: center;
          text-align: center; overflow: hidden;
        }
        .we-hero-bg {
          position: absolute; inset: 0;
          background-size: cover; background-position: center;
        }
        .we-hero-overlay {
          position: absolute; inset: 0;
          background: linear-gradient(to bottom, rgba(0,0,0,0.52) 0%, rgba(0,0,0,0.68) 100%);
        }
        .we-hero-content {
          position: relative; z-index: 2;
          max-width: 72rem; margin: 0 auto;
          padding: 0 1.5rem;
        }
        .we-hero h1 {
          font-size: clamp(2.25rem, 5vw, 3rem);
          font-weight: 600; color: #fff; line-height: 1.1;
          letter-spacing: -0.02em; margin-bottom: 1.25rem;
        }
        .we-rating-row {
          display: flex; align-items: center; justify-content: center;
          gap: 0.5rem; margin-bottom: 1.25rem;
          color: rgba(255,255,255,0.85); font-size: 0.875rem;
        }
        .we-stars { color: #fbbf24; letter-spacing: 0.04em; font-size: 1rem; }
        .we-hero-review {
          font-size: 1rem; color: rgba(255,255,255,0.78);
          font-style: italic; line-height: 1.6;
          max-width: 560px; margin: 0 auto 0.5rem;
        }
        .we-hero-review-attr {
          font-size: 0.875rem; color: rgba(255,255,255,0.45);
          margin: 0 auto 2.5rem;
        }
        .we-hero-actions {
          display: flex; align-items: center; justify-content: center;
          gap: 1rem; flex-wrap: wrap;
        }
        .we-cta-primary {
          display: inline-flex; align-items: center; gap: 0.5rem;
          background: #16a34a; color: #fff;
          text-decoration: none; padding: 0.875rem 2rem;
          border-radius: 8px; font-size: 1rem; font-weight: 600;
          transition: background 0.2s, transform 0.15s;
        }
        .we-cta-primary:hover { background: #15803d; transform: translateY(-1px); }
        .we-cta-secondary {
          display: inline-flex; align-items: center;
          background: rgba(255,255,255,0.12); color: #fff;
          text-decoration: none; padding: 0.875rem 2rem;
          border-radius: 8px; font-size: 1rem; font-weight: 600;
          border: 1px solid rgba(255,255,255,0.3);
          transition: background 0.2s;
        }
        .we-cta-secondary:hover { background: rgba(255,255,255,0.2); }

        /* ── SECTION SHELL ── */
        .we-section { padding: 5rem 1.5rem; }
        .we-container { max-width: 72rem; margin: 0 auto; }
        .we-section-header { text-align: center; margin-bottom: 3rem; }
        .we-section-header h2 {
          font-size: clamp(1.5rem, 3vw, 1.875rem);
          font-weight: 600; color: #111827;
          letter-spacing: -0.01em; margin-bottom: 0.5rem;
        }
        .we-section-header p { font-size: 1rem; color: #4b5563; }

        /* ── REVIEWS ── */
        .we-reviews { background: #f9fafb; }
        .we-reviews-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 1.5rem;
        }
        .we-review-card {
          background: #fff; border-radius: 12px;
          padding: 1.5rem; border: 1px solid #f3f4f6;
          box-shadow: 0 1px 4px rgba(0,0,0,0.04);
        }
        .we-review-stars {
          color: #fbbf24; font-size: 0.875rem;
          margin-bottom: 0.75rem; letter-spacing: 0.04em;
        }
        .we-review-text {
          font-size: 1rem; color: #4b5563;
          font-style: italic; line-height: 1.65; margin-bottom: 1rem;
        }
        .we-review-author {
          font-size: 0.875rem; font-weight: 600; color: #111827;
        }

        /* ── GALLERY ── */
        .we-gallery { background: #fff; }
        .we-gallery-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1.5rem;
        }
        .we-gallery-item {
          aspect-ratio: 4/3;
          border-radius: 0.75rem;
          background-size: cover; background-position: center;
          overflow: hidden;
        }
        @media (max-width: 768px) { .we-gallery-grid { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 480px) { .we-gallery-grid { grid-template-columns: 1fr; } }

        /* ── REVIEW INTEL: PILL SECTIONS ── */
        /* Used by: What Customers Say Most / Popular With Customers / The Experience */
        .we-intel-section-light { background: #f9fafb; }
        .we-intel-section-white { background: #fff; }
        .we-pill-grid {
          display: flex; flex-wrap: wrap; gap: 0.75rem;
          justify-content: center;
          max-width: 720px; margin: 0 auto;
        }
        .we-pill {
          display: inline-flex; align-items: center;
          background: #fff; border: 1px solid #e5e7eb;
          border-radius: 999px; padding: 0.5rem 1.25rem;
          font-size: 1rem; color: #111827; font-weight: 500;
          line-height: 1.4;
        }
        .we-intel-section-light .we-pill { background: #fff; }
        .we-intel-section-white .we-pill { background: #f9fafb; border-color: #e5e7eb; }

        /* ── SERVICES FALLBACK ── */
        .we-services { background: #f9fafb; }
        .we-services-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1.5rem;
        }
        .we-service-card {
          background: #fff; border: 1px solid #f3f4f6;
          border-radius: 12px; padding: 1.5rem;
          transition: box-shadow 0.2s;
        }
        .we-service-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.07); }
        .we-service-card h3 {
          font-size: 1rem; font-weight: 600; color: #111827; line-height: 1.4;
        }

        /* ── CTA BANNER ── */
        .we-cta-banner { background: #fff; text-align: center; }
        .we-cta-banner h2 {
          font-size: clamp(1.5rem, 3vw, 1.875rem);
          font-weight: 600; color: #111827;
          letter-spacing: -0.01em; margin-bottom: 0.75rem;
          max-width: 640px; margin-left: auto; margin-right: auto;
        }
        .we-cta-banner p {
          font-size: 1rem; color: #4b5563; margin-bottom: 2rem;
          max-width: 480px; margin-left: auto; margin-right: auto;
        }
        .we-cta-banner-actions { display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap; }
        .we-cta-green {
          display: inline-flex; align-items: center; gap: 0.5rem;
          background: #16a34a; color: #fff;
          text-decoration: none; padding: 0.875rem 2rem;
          border-radius: 8px; font-size: 1rem; font-weight: 600;
          transition: background 0.2s, transform 0.15s;
        }
        .we-cta-green:hover { background: #15803d; transform: translateY(-1px); }

        /* ── MAP ── */
        .we-map { background: #f9fafb; }
        .we-map-wrap {
          max-width: 900px; margin: 0 auto;
          border-radius: 12px; overflow: hidden;
          border: 1px solid #f3f4f6;
          box-shadow: 0 2px 16px rgba(0,0,0,0.06);
        }
        .we-map iframe { display: block; }

        /* ── CONTACT ── */
        .we-contact { background: #fff; text-align: center; }
        .we-contact-inner {
          max-width: 420px; margin: 0 auto;
          display: flex; flex-direction: column; gap: 0.5rem;
        }
        .we-contact-inner p { font-size: 1rem; color: #4b5563; }
        .we-contact-inner a { color: #16a34a; text-decoration: none; font-weight: 600; }
        .we-contact-inner a:hover { text-decoration: underline; }

        /* ── FOOTER ── */
        .we-footer {
          background: #f9fafb; border-top: 1px solid #f3f4f6;
          text-align: center; padding: 2rem 1.5rem;
        }
        .we-footer p { font-size: 0.875rem; color: #9ca3af; }

        /* ── NOTICE STRIP ── */
        .we-notice {
          background: #f0fdf4; border-bottom: 1px solid #bbf7d0;
          text-align: center; padding: 0.625rem 1.5rem;
          font-size: 0.875rem; color: #15803d;
          position: relative; z-index: 200;
        }

        @media (max-width: 640px) {
          .we-nav { padding: 1rem 1.25rem; }
          .we-hero h1 { font-size: 2rem; }
        }
      `}</style>

      {/* NOTICE STRIP */}
      <div className="we-notice">
        This is a preview of how your business could look online
      </div>

      {/* NAV */}
      <nav className="we-nav">
        <div className="we-nav-inner">
          <div className="we-nav-logo">{name}</div>
          <a href={waLink} target="_blank" rel="noopener noreferrer" className="we-nav-cta">
            Claim This Site
          </a>
        </div>
      </nav>

      {/* HERO */}
      <section className="we-hero" style={{ paddingTop: '4rem' }}>
        {hero_image && (
          <div className="we-hero-bg" style={{ backgroundImage: `url(${hero_image})` }} />
        )}
        <div className="we-hero-overlay" />
        <div className="we-hero-content">
          <h1>{name}</h1>

          {rating > 0 && (
            <div className="we-rating-row">
              <span className="we-stars">{stars}</span>
              <span>{rating.toFixed(1)} · {reviews_count.toLocaleString()} Google reviews</span>
            </div>
          )}

          {heroQuote && (
            <>
              <p className="we-hero-review">&ldquo;{heroQuote}&rdquo;</p>
              <p className="we-hero-review-attr">— Google review</p>
            </>
          )}

          <div className="we-hero-actions">
            <a href={waLink} target="_blank" rel="noopener noreferrer" className="we-cta-primary">
              Chat on WhatsApp
            </a>
            <a href="#reviews" className="we-cta-secondary">
              See Reviews
            </a>
          </div>
        </div>
      </section>

      {/* WHAT CUSTOMERS SAY (full review cards) */}
      {reviews.length > 0 && (
        <section className="we-section we-reviews" id="reviews">
          <div className="we-container">
            <div className="we-section-header">
              <h2>What Customers Say</h2>
              <p>{reviews_count.toLocaleString()} reviews on Google</p>
            </div>
            <div className="we-reviews-grid">
              {reviews.slice(0, 5).map((r: Review, i: number) => (
                <div key={i} className="we-review-card">
                  <div className="we-review-stars">{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</div>
                  <p className="we-review-text">&ldquo;{r.text}&rdquo;</p>
                  <p className="we-review-author">{r.author}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* GALLERY */}
      {gallerySlice.length > 0 && (
        <section className="we-section we-gallery">
          <div className="we-container">
            <div className="we-section-header">
              <h2>{has_real_photos ? 'Photos' : 'Gallery'}</h2>
              {has_real_photos && <p>From Google Maps</p>}
            </div>
            <div className="we-gallery-grid">
              {gallerySlice.map((img: string, i: number) => (
                <div
                  key={i}
                  className="we-gallery-item"
                  style={{ backgroundImage: `url(${img})` }}
                />
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ── REVIEW INTEL SECTIONS (replace generic services) ── */}
      {useReviewIntel ? (
        <>
          {/* WHAT CUSTOMERS SAY MOST */}
          {review_intel!.top_highlights.length > 0 && (
            <section className="we-section we-intel-section-light">
              <div className="we-container">
                <div className="we-section-header">
                  <h2>What Customers Say Most</h2>
                </div>
                <div className="we-pill-grid">
                  {review_intel!.top_highlights.map((h: string, i: number) => (
                    <span key={i} className="we-pill">{h}</span>
                  ))}
                </div>
              </div>
            </section>
          )}

          {/* POPULAR WITH CUSTOMERS */}
          {review_intel!.signature_items.length > 0 && (
            <section className="we-section we-intel-section-white">
              <div className="we-container">
                <div className="we-section-header">
                  <h2>Popular With Customers</h2>
                </div>
                <div className="we-pill-grid">
                  {review_intel!.signature_items.map((item: string, i: number) => (
                    <span key={i} className="we-pill">{item}</span>
                  ))}
                </div>
              </div>
            </section>
          )}

          {/* THE EXPERIENCE */}
          {review_intel!.experience_tags.length > 0 && (
            <section className="we-section we-intel-section-light">
              <div className="we-container">
                <div className="we-section-header">
                  <h2>The Experience</h2>
                </div>
                <div className="we-pill-grid">
                  {review_intel!.experience_tags.map((tag: string, i: number) => (
                    <span key={i} className="we-pill">{tag}</span>
                  ))}
                </div>
              </div>
            </section>
          )}
        </>
      ) : (
        /* FALLBACK: minimal services list only when no review intel */
        services.length > 0 && (
          <section className="we-section we-services">
            <div className="we-container">
              <div className="we-section-header">
                <h2>Services</h2>
              </div>
              <div className="we-services-grid">
                {services.map((s: string, i: number) => (
                  <div key={i} className="we-service-card">
                    <h3>{s}</h3>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )
      )}

      {/* CTA BANNER */}
      <section className="we-section we-cta-banner">
        <div className="we-container">
          <h2>Ready to attract more customers?</h2>
          <p>This preview was built from your real Google data. Message us to claim it.</p>
          <div className="we-cta-banner-actions">
            <a href={waLink} target="_blank" rel="noopener noreferrer" className="we-cta-green">
              Chat on WhatsApp
            </a>
          </div>
        </div>
      </section>

      {/* MAP EMBED */}
      {map_embed && (
        <section className="we-section we-map">
          <div className="we-container">
            <div className="we-section-header">
              <h2>Find Us</h2>
              {address && <p>{address}</p>}
            </div>
            <div className="we-map-wrap">
              <iframe
                src={map_embed}
                width="100%"
                height="380"
                style={{ border: 0 }}
                allowFullScreen
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
            </div>
          </div>
        </section>
      )}

      {/* CONTACT */}
      <section className="we-section we-contact" id="contact">
        <div className="we-container">
          <div className="we-section-header">
            <h2>Contact</h2>
          </div>
          <div className="we-contact-inner">
            {phone && <p><a href={`tel:${phone}`}>{phone}</a></p>}
            {address && <p>{address}</p>}
            {google_maps_url && (
              <p>
                <a href={google_maps_url} target="_blank" rel="noopener noreferrer">
                  View on Google Maps
                </a>
              </p>
            )}
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="we-footer">
        <p>&copy; {new Date().getFullYear()} {name}. All rights reserved.</p>
      </footer>
    </>
  )
}
