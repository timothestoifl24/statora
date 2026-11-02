import { defineConfig, type HeadConfig } from 'vitepress'

const repo = 'https://github.com/timothestoifl24/statora'
const site = 'https://statora.timothestoifl24.dev'
// pages.yml builds main at / (production) and develop at /dev/ (development) into one site.
const dev = process.env.DOCS_CHANNEL === 'development'
const base = dev ? '/dev/' : '/'
// Search engines should only list the production docs; the banner needs room above the nav.
const devHead: HeadConfig[] = dev
  ? [
      ['meta', { name: 'robots', content: 'noindex' }],
      ['style', {}, ':root { --vp-layout-top-height: 40px; }'],
    ]
  : []
const movedPages = [
  'setup/docker-compose',
  'reference/configuration',
  'reference/upgrading',
  'reference/api',
  'reference/images',
  'reference/faq',
  'reference/development',
]
const description =
  'Self-hosted uptime monitoring and status pages: HTTP, TCP, ping, DNS and SQL checks, service groups, incidents, maintenance and SSO in one container.'

export default defineConfig({
  lang: 'en-US',
  base,
  title: 'Statora',
  titleTemplate: ':title | Statora',
  description,
  cleanUrls: true,
  lastUpdated: true,
  sitemap: {
    hostname: `${site}${base}`,
    // These pages only forward their old URLs to where the content moved.
    transformItems: (items) => items.filter((item) => !movedPages.includes(item.url)),
  },
  // Setup guides point readers at their own http://localhost:8000; every other link is checked.
  ignoreDeadLinks: 'localhostLinks',

  head: [
    ['link', { rel: 'icon', href: `${base}brand/favicon.svg`, type: 'image/svg+xml' }],
    ['link', { rel: 'icon', href: `${base}brand/favicon.ico`, sizes: '32x32' }],
    ['link', { rel: 'apple-touch-icon', href: `${base}brand/apple-touch-icon.png` }],
    ['meta', { name: 'theme-color', content: '#1f6feb' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'Statora' }],
    ['meta', { property: 'og:image', content: `${site}/brand/og-image.png` }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    // Ko-fi "Support me" button, in the brand blue. It draws into <body>, so wait for the page to load.
    ['script', { src: 'https://storage.ko-fi.com/cdn/scripts/overlay-widget.js', defer: '' }],
    [
      'script',
      {},
      `window.addEventListener('load', () => kofiWidgetOverlay.draw('timothestoifl24', {
        'type': 'floating-chat',
        'floating-chat.donateButton.text': 'Support me',
        'floating-chat.donateButton.background-color': '#1f6feb',
        'floating-chat.donateButton.text-color': '#fff'
      }))`,
    ],
    ...devHead,
  ],

  themeConfig: {
    logo: { src: '/brand/icon.svg', alt: 'Statora' },
    siteTitle: 'Statora',

    nav: [
      { text: 'Guide', link: '/guide/', activeMatch: '/guide/' },
      { text: 'Screenshots', link: '/screenshots' },
      {
        text: 'Setup',
        activeMatch: '/setup/',
        items: [
          {
            text: 'Deploy',
            items: [
              { text: 'Docker / Podman', link: '/setup/docker' },
              { text: 'Kubernetes', link: '/setup/kubernetes' },
              { text: 'Initial setup', link: '/setup/initial-setup' },
            ],
          },
          {
            items: [
              { text: 'Advanced config', link: '/setup/advanced-config' },
              { text: 'Upgrading', link: '/setup/upgrading' },
              { text: 'REST API', link: '/setup/api' },
            ],
          },
        ],
      },
      {
        text: 'Reference',
        activeMatch: '/reference/',
        items: [
          { text: 'Contributing', link: '/reference/contributing' },
          { text: 'Security policy', link: '/reference/security' },
          { text: 'Changelog', link: '/reference/changelog' },
          { text: 'Releases', link: '/reference/releases' },
        ],
      },
      { text: 'FAQ', link: '/faq' },
    ],

    // One sidebar for the whole site, in the same order as the top navigation.
    sidebar: [
      {
        text: 'Getting started',
        items: [
          { text: 'Overview', link: '/' },
          {
            text: 'Guide',
            link: '/guide/',
            collapsed: true,
            items: [
              { text: 'Monitors', link: '/guide/monitors' },
              { text: 'Groups', link: '/guide/groups' },
              { text: 'Status pages', link: '/guide/status-pages' },
              { text: 'Incidents & maintenance', link: '/guide/incidents' },
              { text: 'Users & sign-in', link: '/guide/authentication' },
              { text: 'API & automation', link: '/guide/api' },
            ],
          },
          { text: 'Screenshots', link: '/screenshots' },
        ],
      },
      {
        text: 'Setup',
        link: '/setup/',
        items: [
          {
            text: 'Deploy',
            collapsed: false,
            items: [
              { text: 'Docker / Podman', link: '/setup/docker' },
              { text: 'Kubernetes', link: '/setup/kubernetes' },
              { text: 'Initial setup', link: '/setup/initial-setup' },
            ],
          },
          { text: 'Advanced config', link: '/setup/advanced-config' },
          { text: 'Upgrading', link: '/setup/upgrading' },
          { text: 'REST API', link: '/setup/api' },
        ],
      },
      {
        text: 'Reference',
        items: [
          { text: 'Contributing', link: '/reference/contributing' },
          { text: 'Security policy', link: '/reference/security' },
          { text: 'Changelog', link: '/reference/changelog' },
          { text: 'Releases', link: '/reference/releases' },
        ],
      },
      { text: 'FAQ', link: '/faq' },
    ],

    // Between the appearance switch and GitHub. Font Awesome's "docker" brand icon (CC BY 4.0).
    socialLinks: [
      {
        icon: {
          svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512"><path fill="currentColor" d="M349.9 236.3h-66.1v-59.4h66.1v59.4zm0-204.3h-66.1v60.7h66.1V32zm78.2 144.8H362v59.4h66.1v-59.4zm-156.3-72.1h-66.1v60.1h66.1v-60.1zm78.1 0h-66.1v60.1h66.1v-60.1zm276.8 100c-14.4-9.7-47.6-13.2-73.1-8.4-3.3-24-16.7-44.9-41.1-63.7l-14-9.3-9.3 14c-18.4 27.8-23.4 73.6-3.7 103.8-8.7 4.7-25.8 11.1-48.4 10.7H2.4c-8.7 50.8 5.8 116.8 44 162.1 37.1 43.9 92.7 66.2 165.4 66.2 157.4 0 273.9-72.5 328.4-204.2 21.4.4 67.6.1 91.3-45.2 1.5-2.5 6.6-13.2 8.5-17.1l-13.3-8.9zm-511.1-27.9h-66v59.4h66.1v-59.4zm78.1 0h-66.1v59.4h66.1v-59.4zm78.1 0h-66.1v59.4h66.1v-59.4zm-78.1-72.1h-66.1v60.1h66.1v-60.1z"/></svg>',
        },
        link: 'https://hub.docker.com/r/timothestoifl24/statora',
        ariaLabel: 'Docker Hub',
      },
      { icon: 'github', link: repo },
    ],
    search: { provider: 'local' },
    editLink: { pattern: `${repo}/edit/develop/docs/:path`, text: 'Edit this page on GitHub' },
    outline: { level: [2, 3] },
    footer: {
      message: 'Released under the <a href="https://github.com/timothestoifl24/statora/blob/main/LICENSE">MIT License</a>.',
      copyright: `© ${new Date().getFullYear()} Timothé Stoifl`,
    },
  },
})
