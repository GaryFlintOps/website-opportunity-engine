import type { Metadata } from 'next'
import WebsiteEngine from '@/components/WebsiteEngine'
import type { BusinessData } from '@/types/business'

// ── Data fetching ─────────────────────────────────────────────────────────────

async function getDemo(slug: string): Promise<BusinessData | null> {
  if (!process.env.API_BASE_URL) {
    throw new Error('API_BASE_URL is not set — add it to Render environment variables')
  }
  try {
    const res = await fetch(`${process.env.API_BASE_URL}/api/demo/${slug}`, {
      cache: 'no-store', // always fresh — demos update when regenerated
    })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

// ── Metadata ──────────────────────────────────────────────────────────────────

export async function generateMetadata({
  params,
}: {
  params: { slug: string }
}): Promise<Metadata> {
  const data = await getDemo(params.slug)
  if (!data) return { title: 'Demo not found' }
  return {
    title: data.name,
    description: data.tagline,
    openGraph: {
      title: data.name,
      description: data.tagline,
      images: data.hero_image ? [{ url: data.hero_image }] : [],
    },
  }
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function DemoPage({
  params,
}: {
  params: { slug: string }
}) {
  const data = await getDemo(params.slug)

  if (!data) {
    const waMsg = encodeURIComponent(
      `Hi — I just visited the website preview you built for my business. Can you finish it for me?`
    )
    const waLink = `https://wa.me/?text=${waMsg}`

    return (
      <main style={{
        fontFamily: 'Inter, -apple-system, sans-serif',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        minHeight: '100vh',
        background: 'linear-gradient(160deg, #0a0a0a 0%, #111827 100%)',
        color: '#e4e6f0',
        textAlign: 'center', padding: '2rem', gap: '1.5rem',
      }}>
        {/* Notice strip */}
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0,
          background: '#1a1a2e',
          color: 'rgba(255,255,255,.72)',
          padding: '0.7rem 1.5rem',
          fontSize: '0.78rem', letterSpacing: '0.03em',
          borderBottom: '1px solid rgba(201,169,110,.2)',
          textAlign: 'center',
        }}>
          ✦ <strong style={{ color: '#c9a96e' }}>This is a preview of how your business could look online</strong>
        </div>

        <div style={{ marginTop: '4rem' }}>
          <div style={{ fontSize: '3rem', marginBottom: '1.5rem' }}>🏗️</div>
          <h1 style={{
            fontSize: 'clamp(1.6rem, 4vw, 2.2rem)',
            fontWeight: 900, color: '#fff',
            marginBottom: '1rem', letterSpacing: '-0.02em',
          }}>
            We&apos;ve started building a preview for this business
          </h1>
          <p style={{
            color: '#9ca3af', maxWidth: '480px', lineHeight: 1.8,
            fontSize: '1rem', marginBottom: '2rem',
          }}>
            If you&apos;re the owner, message us and we&apos;ll finish it for you.
          </p>
          <a
            href={waLink}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
              background: '#25D366', color: '#fff',
              textDecoration: 'none', padding: '1rem 2.5rem',
              fontSize: '1rem', fontWeight: 700,
              letterSpacing: '0.04em', textTransform: 'uppercase',
              borderRadius: '6px',
            }}
          >
            💬 Message Us on WhatsApp
          </a>
        </div>
      </main>
    )
  }

  return <WebsiteEngine data={data} />
}
