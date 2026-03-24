import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Website Opportunity Engine',
  description: 'Powered by real Google Maps data',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
