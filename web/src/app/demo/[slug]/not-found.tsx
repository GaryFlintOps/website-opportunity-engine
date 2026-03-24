export default function NotFound() {
  return (
    <main style={{
      fontFamily: 'Inter, -apple-system, sans-serif',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', background: '#0f1117', color: '#e4e6f0',
      textAlign: 'center', padding: '2rem',
    }}>
      <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🔍</div>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.75rem' }}>
        Demo not found
      </h1>
      <p style={{ color: '#8b8fa8', maxWidth: '400px', lineHeight: 1.6 }}>
        This demo hasn&apos;t been generated yet. Go to the dashboard, find the lead,
        and click <strong style={{ color: '#6c63ff' }}>Generate Demo</strong>.
      </p>
    </main>
  )
}
