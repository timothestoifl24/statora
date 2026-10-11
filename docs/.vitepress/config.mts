import { defineConfig } from 'vitepress'

const repo = 'https://github.com/timothestoifl24/statora'
const site = 'https://statora.stoifl.app'
const description =
  'Self-hosted uptime monitoring and public status pages: HTTP, TCP, ping and DNS checks, stack and redundancy groups, incidents, maintenance, LDAP/OIDC/SAML sign-in and a Terraform-ready API.'

export default defineConfig({
  lang: 'en-US',
  title: 'Statora',
  titleTemplate: ':title · Statora',
  description,
  cleanUrls: true,
  lastUpdated: true,
  sitemap: { hostname: site },
  // Setup guides point readers at their own http://localhost:8000; every other link is checked.
  ignoreDeadLinks: 'localhostLinks',

  head: [
    ['link', { rel: 'icon', href: '/brand/favicon.svg', type: 'image/svg+xml' }],
    ['link', { rel: 'icon', href: '/brand/favicon.ico', sizes: '32x32' }],
    ['link', { rel: 'apple-touch-icon', href: '/brand/apple-touch-icon.png' }],
    ['meta', { name: 'theme-color', content: '#1f6feb' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'Statora' }],
    ['meta', { property: 'og:image', content: `${site}/brand/og-image.png` }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
  ],

  themeConfig: {
    logo: { src: '/brand/icon.svg', alt: 'Statora' },
    siteTitle: 'Statora',

    nav: [
      { text: 'Guide', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Setup', link: '/setup/', activeMatch: '/setup/(index|docker|docker-compose)?$' },
      { text: 'Kubernetes', link: '/setup/kubernetes' },
      { text: 'Screenshots', link: '/screenshots' },
      {
        text: 'Reference',
        activeMatch: '/reference/',
        items: [
          { text: 'Configuration', link: '/reference/configuration' },
          { text: 'REST API', link: '/reference/api' },
          { text: 'Upgrading', link: '/reference/upgrading' },
          { text: 'FAQ', link: '/reference/faq' },
          { text: 'Development', link: '/reference/development' },
          { text: 'Changelog', link: '/reference/changelog' },
          { text: 'Container images', link: '/reference/images' },
          { text: 'Contributing', link: 'https://github.com/timothestoifl24/statora/blob/main/CONTRIBUTING.md' },
          { text: 'Security policy', link: 'https://github.com/timothestoifl24/statora/blob/main/SECURITY.md' },
        ],
      },
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Guide',
          items: [
            { text: 'Overview', link: '/guide/' },
            { text: 'Monitors', link: '/guide/monitors' },
            { text: 'Groups', link: '/guide/groups' },
            { text: 'Status pages', link: '/guide/status-pages' },
            { text: 'Incidents & maintenance', link: '/guide/incidents' },
            { text: 'Users & sign-in', link: '/guide/authentication' },
            { text: 'API & automation', link: '/guide/api' },
          ],
        },
      ],
      '/setup/': [
        {
          text: 'Setup',
          items: [
            { text: 'Choose a method', link: '/setup/' },
            { text: 'Docker', link: '/setup/docker' },
            { text: 'Docker Compose', link: '/setup/docker-compose' },
            { text: 'Kubernetes', link: '/setup/kubernetes' },
          ],
        },
        {
          text: 'Next steps',
          items: [
            { text: 'Configuration', link: '/reference/configuration' },
            { text: 'Upgrading', link: '/reference/upgrading' },
          ],
        },
      ],
      '/reference/': [
        {
          text: 'Reference',
          items: [
            { text: 'Configuration', link: '/reference/configuration' },
            { text: 'REST API', link: '/reference/api' },
            { text: 'Upgrading', link: '/reference/upgrading' },
            { text: 'FAQ', link: '/reference/faq' },
            { text: 'Development', link: '/reference/development' },
            { text: 'Changelog', link: '/reference/changelog' },
            { text: 'Container images', link: '/reference/images' },
          ],
        },
        {
          text: 'Project',
          items: [
            { text: 'Contributing', link: 'https://github.com/timothestoifl24/statora/blob/main/CONTRIBUTING.md' },
            { text: 'Security policy', link: 'https://github.com/timothestoifl24/statora/blob/main/SECURITY.md' },
            { text: 'License (MIT)', link: 'https://github.com/timothestoifl24/statora/blob/main/LICENSE' },
          ],
        },
      ],
    },

    socialLinks: [{ icon: 'github', link: repo }],
    search: { provider: 'local' },
    editLink: { pattern: `${repo}/edit/develop/docs/:path`, text: 'Edit this page on GitHub' },
    outline: { level: [2, 3] },
    footer: {
      message: 'Released under the <a href="https://github.com/timothestoifl24/statora/blob/main/LICENSE">MIT License</a>.',
      copyright: `© ${new Date().getFullYear()} Timothé Stoifl`,
    },
  },
})
