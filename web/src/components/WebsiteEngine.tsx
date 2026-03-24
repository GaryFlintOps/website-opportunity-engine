import type { BusinessData, Review } from '@/types/business'

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderStars(rating: number): string {
  const full  = Math.floor(rating)
  const half  = rating - full >= 0.3 ? 1 : 0
  const empty = 5 - full - half
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty)
}

function serviceIcon(service: string): string {
  const s = service.toLowerCase()
  const map: [string, string][] = [
    ['espresso', '☕'], ['coffee', '☕'], ['cold brew', '🧊'],
    ['pastry', '🥐'], ['bread', '🍞'], ['cake', '🎂'], ['croissant', '🥐'],
    ['hair', '✂️'], ['cut', '✂️'], ['colour', '🎨'], ['color', '🎨'],
    ['beard', '🪒'], ['shave', '🪒'],
    ['train', '💪'], ['class', '🏋️'], ['nutrition', '🥗'], ['membership', '🎫'],
    ['check', '🦷'], ['teeth', '🦷'], ['orthodon', '😁'], ['emergen', '🚨'],
    ['wiring', '⚡'], ['electric', '⚡'], ['panel', '🔌'], ['smart', '📱'],
    ['pipe', '🔧'], ['drain', '🚿'], ['bathroom', '🛁'], ['repair', '🔧'],
    ['massage', '💆'], ['facial', '✨'], ['couple', '💑'], ['detox', '🌿'],
    ['wedding', '💐'], ['florist', '🌸'], ['delivery', '📦'], ['event', '🎉'],
    ['brake', '🚗'], ['tyre', '🚗'], ['diagnostic', '🔍'],
    ['room', '🛏️'], ['conference', '📊'], ['concierge', '🔔'],
    ['dining', '🍽️'], ['catering', '🍴'], ['takeaway', '🥡'],
    ['service', '⭐'], ['consultation', '💬'], ['premium', '🏆'], ['satisfaction', '✅'],
  ]
  for (const [kw, icon] of map) {
    if (s.includes(kw)) return icon
  }
  return '✦'
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function WebsiteEngine({ data }: { data: BusinessData }) {
  const {
    name, address, phone,
    rating, reviews_count, google_maps_url,
    hero_image, gallery_images,
    has_real_photos, has_real_reviews,
    reviews, map_embed, services,
  } = data

  const stars = rating ? renderStars(rating) : ''

  // WhatsApp deep-link — strip all non-digits from phone
  const waPhone = (phone || '').replace(/\D/g, '')
  const waMsg   = encodeURIComponent(
    `Hi ${name} — I built a website preview for you using your Google reviews. Can I show you how this could bring you more customers?`
  )
  const waLink  = waPhone ? `https://wa.me/${waPhone}?text=${waMsg}` : '#contact'

  return (
    <>
      {/* ── Inline styles — self-contained, no Tailwind required ── */}
      <style>{`
        :root {
          --dark:   #0a0a0a;
          --accent: #c9a96e;
          --light:  #f9f6f1;
          --text:   #3a3a3a;
          --muted:  #888;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', -apple-system, sans-serif; color: var(--text); background: #fff; line-height: 1.6; }

        /* NAV */
        .we-nav {
          position: fixed; top: 0; left: 0; right: 0; z-index: 100;
          display: flex; align-items: center; justify-content: space-between;
          padding: 1.2rem 2.5rem;
          background: rgba(10,10,10,0.88);
          backdrop-filter: blur(12px);
        }
        .we-nav-logo { color: #fff; font-size: 1.05rem; font-weight: 700; letter-spacing: 0.02em; }
        .we-nav-cta {
          background: var(--accent); color: #000;
          text-decoration: none; padding: 0.55rem 1.4rem;
          border-radius: 4px; font-size: 0.82rem; font-weight: 700;
          letter-spacing: 0.06em; text-transform: uppercase;
          transition: opacity 0.2s;
        }
        .we-nav-cta:hover { opacity: 0.85; }

        /* HERO */
        .we-hero {
          position: relative; min-height: 100vh;
          display: flex; align-items: center; justify-content: center;
          text-align: center; overflow: hidden;
        }
        .we-hero-bg {
          position: absolute; inset: 0;
          background-size: cover; background-position: center; background-repeat: no-repeat;
        }
        .we-hero-overlay {
          position: absolute; inset: 0;
          background: linear-gradient(160deg, rgba(0,0,0,.60) 0%, rgba(0,0,0,.72) 50%, rgba(0,0,0,.88) 100%);
        }
        .we-hero-content {
          position: relative; z-index: 2;
          max-width: 900px; padding: 3rem 2rem;
        }
        .we-eyebrow {
          display: inline-block; background: var(--accent); color: #000;
          font-size: 0.72rem; font-weight: 700;
          letter-spacing: 0.18em; text-transform: uppercase;
          padding: 0.4rem 1.1rem; border-radius: 2px; margin-bottom: 2rem;
        }
        .we-hero h1 {
          font-size: clamp(3rem, 8vw, 5.5rem);
          font-weight: 900; color: #fff; line-height: 1.05;
          margin-bottom: 1.8rem; letter-spacing: -0.03em;
          text-shadow: 0 2px 24px rgba(0,0,0,.45), 0 1px 4px rgba(0,0,0,.3);
        }
        .we-tagline {
          font-size: clamp(1.1rem, 2.8vw, 1.5rem);
          color: rgba(255,255,255,.88); font-weight: 300;
          margin-bottom: 2.5rem; max-width: 600px;
          margin-left: auto; margin-right: auto; line-height: 1.5;
          text-shadow: 0 1px 8px rgba(0,0,0,.35);
        }
        .we-rating-bar {
          display: flex; align-items: center; justify-content: center;
          gap: 0.6rem; margin-bottom: 3rem;
          color: rgba(255,255,255,.8); font-size: 0.9rem;
        }
        .we-stars { color: var(--accent); font-size: 1.1rem; letter-spacing: 0.05em; }
        .we-cta {
          display: inline-block;
          background: var(--accent); color: #000;
          text-decoration: none; padding: 1.1rem 2.8rem;
          font-size: 1rem; font-weight: 700;
          letter-spacing: 0.06em; text-transform: uppercase;
          border-radius: 4px; transition: transform 0.2s, opacity 0.2s;
        }
        .we-cta:hover { transform: translateY(-2px); opacity: 0.9; }

        /* SHARED SECTION */
        .we-section { padding: 5.5rem 2rem; }
        .we-label {
          font-size: 0.72rem; font-weight: 700;
          letter-spacing: 0.18em; text-transform: uppercase;
          color: var(--accent); margin-bottom: 0.7rem;
        }
        .we-section h2 {
          font-size: clamp(1.8rem, 4vw, 2.6rem);
          font-weight: 800; color: var(--dark);
          letter-spacing: -0.02em; margin-bottom: 1rem;
        }
        .we-sub {
          color: var(--muted); font-size: 0.95rem;
          margin-bottom: 3rem;
          max-width: 560px; margin-left: auto; margin-right: auto;
        }

        /* REVIEWS */
        .we-reviews { background: var(--light); text-align: center; }
        .we-reviews-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 1.5rem; max-width: 1080px; margin: 0 auto;
        }
        .we-review-card {
          background: #fff; border-radius: 12px;
          padding: 2rem 1.75rem; text-align: left;
          border-top: 3px solid var(--accent);
          box-shadow: 0 2px 16px rgba(0,0,0,.05);
        }
        .we-review-stars { color: var(--accent); font-size: 0.88rem; margin-bottom: 0.8rem; letter-spacing: 0.04em; }
        .we-review-text {
          font-size: 0.9rem; color: var(--text);
          font-style: italic; line-height: 1.7; margin-bottom: 1rem;
        }
        .we-review-author {
          font-size: 0.74rem; font-weight: 700;
          color: var(--accent); letter-spacing: 0.08em; text-transform: uppercase;
        }

        /* GALLERY */
        .we-gallery { background: var(--dark); text-align: center; }
        .we-gallery h2 { color: #fff; }
        .we-gallery .we-sub { color: rgba(255,255,255,.4); }
        .we-gallery-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 1rem; max-width: 1100px; margin: 0 auto;
        }
        .we-gallery-item {
          height: 220px; border-radius: 10px;
          background-size: cover; background-position: center;
          transition: transform 0.25s;
        }
        .we-gallery-item:hover { transform: scale(1.02); }

        /* SERVICES */
        .we-services { background: #fff; text-align: center; }
        .we-services-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1.5rem; max-width: 960px; margin: 0 auto;
        }
        .we-service-card {
          border: 1px solid #eee; border-radius: 10px;
          padding: 2rem 1.5rem;
          transition: box-shadow 0.2s, border-color 0.2s;
        }
        .we-service-card:hover { box-shadow: 0 4px 24px rgba(0,0,0,.08); border-color: var(--accent); }
        .we-service-icon { font-size: 1.8rem; margin-bottom: 0.75rem; }
        .we-service-card h3 { font-size: 0.92rem; font-weight: 700; color: var(--dark); }

        /* CTA BANNER */
        .we-cta-banner { background: var(--dark); text-align: center; }
        .we-cta-banner h2 { color: #fff; margin-bottom: 1rem; }
        .we-cta-banner p { color: rgba(255,255,255,.55); margin-bottom: 2.5rem; max-width: 480px; margin-left: auto; margin-right: auto; }

        /* MAP */
        .we-map { background: var(--light); text-align: center; }
        .we-map-wrap {
          max-width: 900px; margin: 0 auto;
          border-radius: 12px; overflow: hidden;
          box-shadow: 0 4px 32px rgba(0,0,0,.1);
        }
        .we-map iframe { display: block; }

        /* CONTACT */
        .we-contact { background: var(--light); text-align: center; }
        .we-contact-inner { max-width: 520px; margin: 2rem auto 0; }
        .we-contact-inner p { margin-bottom: 0.6rem; color: #555; font-size: 0.95rem; }
        .we-contact-inner a { color: var(--accent); text-decoration: none; font-weight: 600; }
        .we-contact-inner a:hover { text-decoration: underline; }

        /* FOOTER */
        .we-footer {
          background: var(--dark); color: rgba(255,255,255,.35);
          text-align: center; padding: 2rem; font-size: 0.78rem;
        }
        .we-footer strong { color: rgba(255,255,255,.65); }

        /* NOTICE STRIP */
        .we-notice {
          background: #1a1a2e;
          color: rgba(255,255,255,.72);
          text-align: center; padding: 0.8rem 1.5rem;
          font-size: 0.78rem; letter-spacing: 0.03em;
          position: relative; z-index: 200;
          border-bottom: 1px solid rgba(201,169,110,.25);
        }
        .we-notice strong { color: var(--accent); }

        /* BADGE */
        .we-badge {
          position: fixed; bottom: 1.5rem; right: 1.5rem;
          background: var(--accent); color: #000;
          font-size: 0.68rem; font-weight: 700;
          letter-spacing: 0.08em; text-transform: uppercase;
          padding: 0.45rem 1rem; border-radius: 999px;
          z-index: 9999; box-shadow: 0 4px 16px rgba(0,0,0,.3);
        }

        /* WHATSAPP CTA */
        .we-cta-wa {
          display: inline-flex; align-items: center; gap: 0.5rem;
          background: #25D366; color: #fff;
          text-decoration: none; padding: 1.1rem 2.8rem;
          font-size: 1rem; font-weight: 700;
          letter-spacing: 0.04em; text-transform: uppercase;
          border-radius: 4px; transition: transform 0.2s, opacity 0.2s;
        }
        .we-cta-wa:hover { transform: translateY(-2px); opacity: 0.9; }

        @media (max-width: 640px) {
          .we-nav { padding: 1rem 1.25rem; }
          .we-gallery-grid { grid-template-columns: 1fr 1fr; }
        }
      `}</style>

      {/* DEMO NOTICE STRIP */}
      <div className="we-notice">
        ✦ <strong>This is a preview of how your business could look online</strong>
      </div>

      {/* Preview badge */}
      <div className="we-badge">Preview</div>

      {/* NAV */}
      <nav className="we-nav">
        <div className="we-nav-logo">{name}</div>
        <a href={waLink} target="_blank" rel="noopener noreferrer" className="we-nav-cta">
          Claim This Site
        </a>
      </nav>

      {/* HERO */}
      <section className="we-hero">
        <div className="we-hero-bg" style={{ backgroundImage: `url(${hero_image})` }} />
        <div className="we-hero-overlay" />
        <div className="we-hero-content">
          <span className="we-eyebrow">{name}</span>
          <h1>This website could bring you more customers</h1>
          <p className="we-tagline">We built this using your Google reviews and real business data</p>
          {rating > 0 && (
            <div className="we-rating-bar">
              <span className="we-stars">{stars}</span>
              <span>{rating.toFixed(1)} · {reviews_count.toLocaleString()} reviews on Google</span>
            </div>
          )}
          <a href={waLink} target="_blank" rel="noopener noreferrer" className="we-cta-wa">
            💬 Chat on WhatsApp →
          </a>
        </div>
      </section>

      {/* REAL REVIEWS */}
      {reviews.length > 0 && (
        <section className="we-section we-reviews">
          <p className="we-label">What customers say</p>
          <h2>Real Reviews</h2>
          <p className="we-sub">From Google Maps · {reviews_count.toLocaleString()} total reviews</p>
          <div className="we-reviews-grid">
            {reviews.slice(0, 5).map((r: Review, i: number) => (
              <div key={i} className="we-review-card">
                <div className="we-review-stars">{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</div>
                <p className="we-review-text">"{r.text}"</p>
                <p className="we-review-author">— {r.author}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* PHOTO GALLERY */}
      {gallery_images.length > 0 && (
        <section className="we-section we-gallery">
          <p className="we-label">{has_real_photos ? 'Photos from Google Maps' : 'Example photos'}</p>
          <h2>Take a Look Inside</h2>
          <p className="we-sub">&nbsp;</p>
          <div className="we-gallery-grid">
            {gallery_images.slice(0, 6).map((img: string, i: number) => (
              <div
                key={i}
                className="we-gallery-item"
                style={{ backgroundImage: `url(${img})` }}
              />
            ))}
          </div>
        </section>
      )}

      {/* SERVICES */}
      <section className="we-section we-services">
        <p className="we-label">What we offer</p>
        <h2>Our Services</h2>
        <div className="we-services-grid">
          {services.map((s: string, i: number) => (
            <div key={i} className="we-service-card">
              <div className="we-service-icon">{serviceIcon(s)}</div>
              <h3>{s}</h3>
            </div>
          ))}
        </div>
      </section>

      {/* CTA BANNER */}
      <section className="we-section we-cta-banner">
        <h2>This isn&apos;t just a website — it&apos;s designed to bring you more customers</h2>
        <p>This demo was built specifically for your business using real Google data. Message us and we&apos;ll show you exactly how it works.</p>
        <a href={waLink} target="_blank" rel="noopener noreferrer" className="we-cta-wa">
          💬 Chat on WhatsApp →
        </a>
      </section>

      {/* MAP EMBED */}
      {map_embed && (
        <section className="we-section we-map">
          <p className="we-label">Find us</p>
          <h2>We&apos;re Here for You</h2>
          {address && <p className="we-sub">{address}</p>}
          <div className="we-map-wrap">
            <iframe
              src={map_embed}
              width="100%"
              height="380"
              style={{ border: 0, borderRadius: '12px' }}
              allowFullScreen
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
            />
          </div>
        </section>
      )}

      {/* CONTACT */}
      <section className="we-section we-contact" id="contact">
        <p className="we-label">Contact</p>
        <h2>Find Us</h2>
        <div className="we-contact-inner">
          {phone && <p><a href={`tel:${phone}`}>📞 {phone}</a></p>}
          {address && <p>📍 {address}</p>}
          {google_maps_url && (
            <p>
              <a href={google_maps_url} target="_blank" rel="noopener noreferrer">
                View on Google Maps ↗
              </a>
            </p>
          )}
        </div>
      </section>

      {/* FOOTER */}
      <footer className="we-footer">
        <p>&copy; 2025 <strong>{name}</strong>. All rights reserved.</p>
      </footer>
    </>
  )
}
