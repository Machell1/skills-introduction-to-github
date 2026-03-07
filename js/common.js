/* ===== AIToolsHub - Common JavaScript ===== */

const SITE_NAME = 'AIToolsHub';
const BASE_URL = 'https://machell1.github.io/skills-introduction-to-github';
const ADSENSE_PUB_ID = ''; // Paste your AdSense publisher ID here

/* ===== AI Tools Database ===== */
const TOOLS = [
  {
    slug: 'chatgpt',
    name: 'ChatGPT',
    tagline: 'The most popular AI chatbot by OpenAI',
    description: 'ChatGPT is a conversational AI assistant by OpenAI that can answer questions, write content, brainstorm ideas, debug code, and much more. Built on GPT-4, it offers both free and premium tiers.',
    icon: '&#129302;',
    category: 'chatbots',
    pricing: 'freemium',
    rating: 4.8,
    url: 'https://chat.openai.com',
    features: ['Conversational AI', 'Code generation', 'Content writing', 'Image generation (DALL-E)', 'Web browsing', 'Plugin ecosystem'],
    pros: ['Most versatile AI assistant', 'Free tier available', 'Huge plugin marketplace', 'Excellent at coding tasks', 'Supports image input and generation'],
    cons: ['GPT-4 requires $20/mo subscription', 'Can hallucinate facts', 'Usage limits on free tier', 'No real-time data on free plan'],
    plans: [
      { name: 'Free', price: '$0', features: 'GPT-3.5, limited GPT-4o access' },
      { name: 'Plus', price: '$20/mo', features: 'GPT-4, DALL-E, browsing, plugins' },
      { name: 'Team', price: '$25/user/mo', features: 'Workspace, admin controls, higher limits' },
      { name: 'Enterprise', price: 'Custom', features: 'Unlimited GPT-4, security, SSO' }
    ]
  },
  {
    slug: 'claude',
    name: 'Claude',
    tagline: 'Thoughtful AI assistant by Anthropic',
    description: 'Claude is an AI assistant by Anthropic known for long-context conversations, careful reasoning, and strong writing ability. It excels at analysis, coding, and detailed content creation with a 200K token context window.',
    icon: '&#128172;',
    category: 'chatbots',
    pricing: 'freemium',
    rating: 4.7,
    url: 'https://claude.ai',
    features: ['200K token context window', 'Document analysis', 'Code generation', 'Creative writing', 'Research assistance', 'Vision capabilities'],
    pros: ['Largest context window available', 'Excellent at nuanced writing', 'Strong reasoning abilities', 'Good at following complex instructions', 'Less prone to hallucination'],
    cons: ['Smaller plugin ecosystem than ChatGPT', 'Pro plan required for heavy use', 'No image generation', 'Fewer integrations'],
    plans: [
      { name: 'Free', price: '$0', features: 'Limited daily messages' },
      { name: 'Pro', price: '$20/mo', features: 'Priority access, higher limits, Claude 3 Opus' },
      { name: 'Team', price: '$25/user/mo', features: 'Collaboration, admin, higher limits' },
      { name: 'Enterprise', price: 'Custom', features: 'SSO, SCIM, custom retention' }
    ]
  },
  {
    slug: 'midjourney',
    name: 'Midjourney',
    tagline: 'Create stunning AI-generated artwork',
    description: 'Midjourney is the leading AI image generation tool, creating photorealistic and artistic images from text descriptions. Popular with designers, marketers, and content creators for producing high-quality visuals.',
    icon: '&#127912;',
    category: 'image',
    pricing: 'paid',
    rating: 4.9,
    url: 'https://midjourney.com',
    features: ['Text-to-image generation', 'Style variation', 'Upscaling', 'Image remixing', 'Pan and zoom', 'Consistent characters'],
    pros: ['Best image quality in the market', 'Incredible artistic styles', 'Active community', 'Fast generation speed', 'Great for professional design work'],
    cons: ['No free tier', 'Runs through Discord (learning curve)', 'Less control than Stable Diffusion', 'Monthly subscription required'],
    plans: [
      { name: 'Basic', price: '$10/mo', features: '200 generations/mo, slow mode' },
      { name: 'Standard', price: '$30/mo', features: '15hr fast, unlimited slow' },
      { name: 'Pro', price: '$60/mo', features: '30hr fast, stealth mode' },
      { name: 'Mega', price: '$120/mo', features: '60hr fast, stealth mode' }
    ]
  },
  {
    slug: 'github-copilot',
    name: 'GitHub Copilot',
    tagline: 'AI pair programmer for your IDE',
    description: 'GitHub Copilot is an AI-powered code completion tool that integrates directly into your IDE. It suggests entire functions, writes tests, explains code, and accelerates development across all major programming languages.',
    icon: '&#128187;',
    category: 'coding',
    pricing: 'paid',
    rating: 4.7,
    url: 'https://github.com/features/copilot',
    features: ['Code completion', 'Chat in IDE', 'Test generation', 'Code explanation', 'Multi-language support', 'CLI assistance'],
    pros: ['Deep IDE integration (VS Code, JetBrains)', 'Excellent code suggestions', 'Understands project context', 'Saves significant development time', 'Free for students and OSS maintainers'],
    cons: ['$10-19/mo for professionals', 'Occasionally suggests incorrect code', 'Privacy concerns with code telemetry', 'Best with popular languages/frameworks'],
    plans: [
      { name: 'Individual', price: '$10/mo', features: 'Code completion, chat, CLI' },
      { name: 'Business', price: '$19/user/mo', features: 'Organization management, policy controls' },
      { name: 'Enterprise', price: '$39/user/mo', features: 'Fine-tuned models, security' }
    ]
  },
  {
    slug: 'cursor',
    name: 'Cursor',
    tagline: 'The AI-first code editor',
    description: 'Cursor is a VS Code fork built from the ground up for AI-assisted development. It features intelligent code completion, natural language editing, and the ability to reference your entire codebase in conversations.',
    icon: '&#9999;',
    category: 'coding',
    pricing: 'freemium',
    rating: 4.8,
    url: 'https://cursor.com',
    features: ['AI code editing', 'Codebase-aware chat', 'Multi-file editing', 'Tab completion', 'Natural language commands', 'VS Code compatibility'],
    pros: ['Understands entire codebase context', 'Can edit multiple files at once', 'Natural language code changes', 'Built on VS Code (familiar UI)', 'Very fast completions'],
    cons: ['Relatively new product', 'Free tier has limited AI requests', 'Heavy resource usage', 'Some VS Code extensions have issues'],
    plans: [
      { name: 'Hobby', price: '$0', features: '2000 completions, 50 premium requests/mo' },
      { name: 'Pro', price: '$20/mo', features: 'Unlimited completions, 500 premium/mo' },
      { name: 'Business', price: '$40/user/mo', features: 'Admin, enforce privacy, SAML SSO' }
    ]
  },
  {
    slug: 'jasper',
    name: 'Jasper',
    tagline: 'AI marketing content platform',
    description: 'Jasper is an enterprise-grade AI content platform built specifically for marketing teams. It generates on-brand blog posts, social media content, ad copy, and email campaigns with built-in brand voice controls.',
    icon: '&#128240;',
    category: 'writing',
    pricing: 'paid',
    rating: 4.5,
    url: 'https://jasper.ai',
    features: ['Brand voice customization', 'Marketing templates', 'Blog post generation', 'Ad copy writing', 'SEO optimization', 'Team collaboration'],
    pros: ['Purpose-built for marketing', 'Strong brand voice controls', 'Many content templates', 'Good team collaboration features', 'Integrates with marketing tools'],
    cons: ['Expensive ($49-125/mo)', 'No free tier', 'Overkill for individual use', 'Output quality varies by template'],
    plans: [
      { name: 'Creator', price: '$49/mo', features: '1 seat, brand voice, SEO mode' },
      { name: 'Pro', price: '$69/mo', features: '3 seats, AI image generation, collaboration' },
      { name: 'Business', price: 'Custom', features: 'Unlimited seats, API, custom workflows' }
    ]
  },
  {
    slug: 'copy-ai',
    name: 'Copy.ai',
    tagline: 'AI-powered copywriting made easy',
    description: 'Copy.ai specializes in generating marketing copy, social media posts, product descriptions, and sales emails. Its workflow automation features help teams scale content production efficiently.',
    icon: '&#128221;',
    category: 'writing',
    pricing: 'freemium',
    rating: 4.4,
    url: 'https://copy.ai',
    features: ['Marketing copy generation', 'Workflow automation', 'Sales email sequences', 'Social media content', 'Product descriptions', 'Infobase knowledge management'],
    pros: ['Generous free tier (2000 words/mo)', 'Great for short-form copy', 'Easy to use interface', 'Good sales and email templates', 'Workflow automation saves time'],
    cons: ['Less suited for long-form content', 'Output can feel generic', 'Advanced features require Pro plan', 'Limited brand customization on free tier'],
    plans: [
      { name: 'Free', price: '$0', features: '2000 words/mo, 1 seat' },
      { name: 'Starter', price: '$36/mo', features: 'Unlimited words, 1 seat, brand voices' },
      { name: 'Advanced', price: '$186/mo', features: '5 seats, workflows, API access' },
      { name: 'Enterprise', price: 'Custom', features: 'Unlimited seats, custom models' }
    ]
  },
  {
    slug: 'runway',
    name: 'Runway',
    tagline: 'AI-powered video creation and editing',
    description: 'Runway is a creative AI platform that offers text-to-video generation, video editing with AI, image generation, and more. Its Gen-2 model can create realistic video clips from text prompts.',
    icon: '&#127910;',
    category: 'video',
    pricing: 'freemium',
    rating: 4.6,
    url: 'https://runwayml.com',
    features: ['Text-to-video (Gen-2)', 'AI video editing', 'Image-to-video', 'Background removal', 'Motion tracking', 'Green screen'],
    pros: ['Leading text-to-video quality', 'Comprehensive video editing suite', 'Free tier to try features', 'Web-based (no install needed)', 'Regular model improvements'],
    cons: ['Video generation is credit-intensive', 'Free tier very limited', 'Generated videos are short (4-16s)', 'Requires learning curve'],
    plans: [
      { name: 'Free', price: '$0', features: '125 credits, 3 projects' },
      { name: 'Standard', price: '$12/mo', features: '625 credits/mo, unlimited projects' },
      { name: 'Pro', price: '$28/mo', features: '2250 credits/mo, 4K upscale' },
      { name: 'Unlimited', price: '$76/mo', features: 'Unlimited Gen-2, priority' }
    ]
  },
  {
    slug: 'synthesia',
    name: 'Synthesia',
    tagline: 'Create AI videos with digital avatars',
    description: 'Synthesia creates professional videos using AI-generated avatars that speak your script in 140+ languages. Perfect for training videos, marketing content, and corporate communications without cameras or actors.',
    icon: '&#127916;',
    category: 'video',
    pricing: 'paid',
    rating: 4.5,
    url: 'https://synthesia.io',
    features: ['150+ AI avatars', '140+ languages', 'Custom avatar creation', 'Screen recording', 'Templates library', 'Brand kit'],
    pros: ['No camera or actors needed', 'Professional-looking results', 'Massive language support', 'Easy script-to-video workflow', 'Good for corporate training'],
    cons: ['Starts at $22/mo', 'Avatar quality varies', 'Limited creative control', 'Videos can feel impersonal'],
    plans: [
      { name: 'Starter', price: '$22/mo', features: '10 minutes video/mo, 9 scenes' },
      { name: 'Creator', price: '$67/mo', features: '30 min/mo, unlimited scenes, custom avatars' },
      { name: 'Enterprise', price: 'Custom', features: 'Unlimited minutes, API, priority' }
    ]
  },
  {
    slug: 'notion-ai',
    name: 'Notion AI',
    tagline: 'AI writing assistant built into Notion',
    description: 'Notion AI brings AI capabilities directly into the Notion workspace. It can summarize documents, generate content, extract action items, translate text, and help organize your knowledge base.',
    icon: '&#128214;',
    category: 'productivity',
    pricing: 'paid',
    rating: 4.4,
    url: 'https://notion.so/product/ai',
    features: ['Document summarization', 'Content generation', 'Action item extraction', 'Translation', 'Q&A from your docs', 'Writing improvement'],
    pros: ['Seamless Notion integration', 'Works with your existing documents', 'Good summarization', 'Natural inline experience', 'Q&A across your workspace'],
    cons: ['$10/mo add-on per member', 'Requires Notion subscription', 'Less powerful than standalone AI tools', 'Limited to Notion ecosystem'],
    plans: [
      { name: 'AI Add-on', price: '$10/member/mo', features: 'Added to any Notion plan' }
    ]
  },
  {
    slug: 'otter-ai',
    name: 'Otter.ai',
    tagline: 'AI meeting transcription and notes',
    description: 'Otter.ai automatically transcribes meetings, generates summaries, and creates action items. It integrates with Zoom, Google Meet, and Microsoft Teams to capture every conversation.',
    icon: '&#127908;',
    category: 'productivity',
    pricing: 'freemium',
    rating: 4.3,
    url: 'https://otter.ai',
    features: ['Real-time transcription', 'Meeting summaries', 'Action items', 'Zoom/Meet/Teams integration', 'Speaker identification', 'Search transcripts'],
    pros: ['Excellent transcription accuracy', 'Automatic meeting notes', 'Good free tier (300 min/mo)', 'Works across all major meeting platforms', 'Searchable transcript archive'],
    cons: ['Some accuracy issues with accents', 'Free tier limits advanced features', 'Best for English content', 'Can be slow to process long recordings'],
    plans: [
      { name: 'Basic', price: '$0', features: '300 min/mo, 30 min per conversation' },
      { name: 'Pro', price: '$16.99/mo', features: '1200 min/mo, 90 min per conversation' },
      { name: 'Business', price: '$30/user/mo', features: '6000 min/mo, admin controls' },
      { name: 'Enterprise', price: 'Custom', features: 'Unlimited, SSO, custom deployment' }
    ]
  },
  {
    slug: 'canva-ai',
    name: 'Canva AI',
    tagline: 'AI-powered design for everyone',
    description: 'Canva integrates AI features including Magic Design, text-to-image, background removal, and Magic Write. It makes professional design accessible to anyone, now supercharged with AI capabilities.',
    icon: '&#127928;',
    category: 'design',
    pricing: 'freemium',
    rating: 4.6,
    url: 'https://canva.com',
    features: ['Magic Design (auto layouts)', 'Text-to-image', 'Background remover', 'Magic Write', 'Magic Eraser', 'Brand Kit'],
    pros: ['Easiest design tool for non-designers', 'AI features included in Pro plan', 'Massive template library', 'Great for social media graphics', 'Collaborative editing'],
    cons: ['AI features limited on free plan', 'Pro is $13/mo per person', 'Less control than Photoshop/Figma', 'AI image quality behind Midjourney'],
    plans: [
      { name: 'Free', price: '$0', features: 'Basic AI features, limited templates' },
      { name: 'Pro', price: '$13/mo', features: 'All AI features, premium templates, brand kit' },
      { name: 'Teams', price: '$10/person/mo', features: 'Collaboration, brand controls' },
      { name: 'Enterprise', price: 'Custom', features: 'SSO, advanced brand controls' }
    ]
  },
  {
    slug: 'grammarly',
    name: 'Grammarly',
    tagline: 'AI writing assistant for error-free content',
    description: 'Grammarly uses AI to check grammar, spelling, tone, and clarity across everything you write. It works in browsers, emails, docs, and social media with real-time suggestions.',
    icon: '&#9989;',
    category: 'writing',
    pricing: 'freemium',
    rating: 4.6,
    url: 'https://grammarly.com',
    features: ['Grammar and spelling check', 'Tone detection', 'Clarity improvements', 'Plagiarism detection', 'GrammarlyGO AI writing', 'Browser extension'],
    pros: ['Works everywhere you write', 'Excellent grammar correction', 'Helpful tone suggestions', 'Good free tier', 'GrammarlyGO generates content'],
    cons: ['Premium is $12/mo', 'Can be overly prescriptive', 'Free tier misses advanced issues', 'Plagiarism checker only on Premium'],
    plans: [
      { name: 'Free', price: '$0', features: 'Basic grammar, spelling, punctuation' },
      { name: 'Premium', price: '$12/mo', features: 'Advanced suggestions, tone, plagiarism, GrammarlyGO' },
      { name: 'Business', price: '$15/member/mo', features: 'Style guides, brand tones, analytics' }
    ]
  },
  {
    slug: 'dall-e',
    name: 'DALL-E 3',
    tagline: 'OpenAI\'s text-to-image AI model',
    description: 'DALL-E 3 by OpenAI generates high-quality images from text descriptions. Integrated into ChatGPT Plus, it produces accurate, detailed images with excellent text rendering and prompt understanding.',
    icon: '&#128444;',
    category: 'image',
    pricing: 'freemium',
    rating: 4.5,
    url: 'https://openai.com/dall-e-3',
    features: ['Text-to-image generation', 'Integrated in ChatGPT', 'Excellent text rendering', 'Inpainting', 'Outpainting', 'API access'],
    pros: ['Best text rendering in images', 'Very good prompt understanding', 'Integrated into ChatGPT workflow', 'API available for developers', 'Free access via Bing Image Creator'],
    cons: ['Limited generations on free tier', 'Less artistic control than Midjourney', 'Content policy restrictions', 'Quality inconsistent with complex scenes'],
    plans: [
      { name: 'Free (via Bing)', price: '$0', features: 'Limited daily generations via Bing' },
      { name: 'ChatGPT Plus', price: '$20/mo', features: 'DALL-E 3 in ChatGPT' },
      { name: 'API', price: '$0.04-0.12/image', features: 'Pay per generation' }
    ]
  },
  {
    slug: 'perplexity',
    name: 'Perplexity AI',
    tagline: 'AI-powered search and research assistant',
    description: 'Perplexity is an AI search engine that provides cited, sourced answers to your questions. It combines web search with AI analysis to deliver accurate, up-to-date information with references.',
    icon: '&#128270;',
    category: 'productivity',
    pricing: 'freemium',
    rating: 4.6,
    url: 'https://perplexity.ai',
    features: ['Cited AI answers', 'Real-time web search', 'Follow-up questions', 'Collections (saved research)', 'File upload analysis', 'Focus modes'],
    pros: ['Always provides sources/citations', 'Up-to-date information', 'Great for research', 'Clean, focused interface', 'Free tier is very generous'],
    cons: ['Pro model limited on free tier', 'Less creative than ChatGPT', 'Can sometimes cite unreliable sources', 'Limited in creative writing tasks'],
    plans: [
      { name: 'Free', price: '$0', features: 'Unlimited quick searches, 5 Pro searches/day' },
      { name: 'Pro', price: '$20/mo', features: 'Unlimited Pro searches, file upload, API credits' }
    ]
  },
  {
    slug: 'elevenlabs',
    name: 'ElevenLabs',
    tagline: 'Realistic AI voice generation and cloning',
    description: 'ElevenLabs creates the most natural-sounding AI voices available. It offers text-to-speech, voice cloning, and dubbing in 29 languages, used by content creators, audiobook producers, and businesses.',
    icon: '&#127911;',
    category: 'audio',
    pricing: 'freemium',
    rating: 4.7,
    url: 'https://elevenlabs.io',
    features: ['Text-to-speech', 'Voice cloning', 'Voice library', '29 languages', 'Speech-to-speech', 'Dubbing'],
    pros: ['Most realistic AI voices', 'Excellent voice cloning quality', 'Multi-language support', 'Good free tier (10K chars/mo)', 'API for developers'],
    cons: ['Premium plans get expensive', 'Voice cloning raises ethical concerns', 'Free tier limited characters', 'Some voices sound better than others'],
    plans: [
      { name: 'Free', price: '$0', features: '10,000 chars/mo, 3 custom voices' },
      { name: 'Starter', price: '$5/mo', features: '30,000 chars/mo, 10 custom voices' },
      { name: 'Creator', price: '$22/mo', features: '100,000 chars/mo, 30 custom voices' },
      { name: 'Pro', price: '$99/mo', features: '500,000 chars/mo, 160 custom voices' }
    ]
  },
  {
    slug: 'leonardo-ai',
    name: 'Leonardo.ai',
    tagline: 'AI image generation with fine control',
    description: 'Leonardo.ai is a versatile AI image generation platform offering fine-tuned models, real-time canvas editing, and specialized tools for game assets, concept art, and graphic design.',
    icon: '&#127913;',
    category: 'image',
    pricing: 'freemium',
    rating: 4.5,
    url: 'https://leonardo.ai',
    features: ['Multiple AI models', 'Real-time canvas', 'Model fine-tuning', 'Image-to-image', 'Texture generation', 'Motion (video)'],
    pros: ['Generous free tier (150 tokens/day)', 'Multiple models to choose from', 'Fine-tuning for custom styles', 'Good for game/design assets', 'Real-time generation on canvas'],
    cons: ['UI can be overwhelming', 'Quality varies by model', 'Advanced features require subscription', 'Less consistent than Midjourney'],
    plans: [
      { name: 'Free', price: '$0', features: '150 tokens/day, basic models' },
      { name: 'Apprentice', price: '$12/mo', features: '8500 tokens/mo, all models' },
      { name: 'Artisan', price: '$30/mo', features: '25,000 tokens/mo, priority' },
      { name: 'Maestro', price: '$60/mo', features: '60,000 tokens/mo, concurrency' }
    ]
  },
  {
    slug: 'surfer-seo',
    name: 'Surfer SEO',
    tagline: 'AI-powered SEO content optimization',
    description: 'Surfer SEO uses AI to analyze top-ranking pages and provides data-driven recommendations for content optimization. It helps writers create SEO-optimized articles that rank on Google.',
    icon: '&#128200;',
    category: 'marketing',
    pricing: 'paid',
    rating: 4.5,
    url: 'https://surferseo.com',
    features: ['Content Editor', 'SERP Analyzer', 'Keyword Research', 'Content Audit', 'AI writing', 'Outline builder'],
    pros: ['Data-driven SEO recommendations', 'Real-time content scoring', 'Good keyword clustering', 'Integrates with Google Docs/WordPress', 'AI writer produces SEO-optimized content'],
    cons: ['Starting at $89/mo', 'Learning curve for beginners', 'Credits-based system can run out', 'Best for English content'],
    plans: [
      { name: 'Essential', price: '$89/mo', features: '15 articles/mo, audit, keyword research' },
      { name: 'Scale', price: '$129/mo', features: '40 articles/mo, auto internal links' },
      { name: 'Scale AI', price: '$219/mo', features: '100 articles/mo, AI writing included' },
      { name: 'Enterprise', price: 'Custom', features: 'Custom limits, priority support' }
    ]
  }
];

const CATEGORIES = [
  { slug: 'chatbots', name: 'AI Chatbots', icon: '&#129302;', desc: 'Conversational AI assistants for Q&A, writing, coding, and research.' },
  { slug: 'writing', name: 'AI Writing', icon: '&#128221;', desc: 'AI tools for content creation, copywriting, grammar, and editing.' },
  { slug: 'image', name: 'AI Image', icon: '&#127912;', desc: 'Generate and edit images using text prompts and AI models.' },
  { slug: 'video', name: 'AI Video', icon: '&#127910;', desc: 'Create and edit videos with AI-powered generation and editing.' },
  { slug: 'coding', name: 'AI Coding', icon: '&#128187;', desc: 'AI-powered code completion, generation, and development tools.' },
  { slug: 'productivity', name: 'Productivity', icon: '&#9889;', desc: 'AI tools for meetings, search, note-taking, and workflow automation.' },
  { slug: 'design', name: 'AI Design', icon: '&#127928;', desc: 'AI-enhanced design tools for graphics, logos, and creative work.' },
  { slug: 'audio', name: 'AI Audio', icon: '&#127911;', desc: 'AI voice generation, music creation, and audio editing.' },
  { slug: 'marketing', name: 'AI Marketing', icon: '&#128200;', desc: 'AI tools for SEO, ads, email marketing, and content strategy.' }
];

/* ===== Navigation ===== */
function renderNav() {
  const isSubPage = window.location.pathname.includes('/tools/') || window.location.pathname.includes('/categories/');
  const basePath = isSubPage ? '../' : '';

  const nav = document.createElement('nav');
  nav.className = 'nav';
  nav.setAttribute('aria-label', 'Main navigation');

  const catLinks = CATEGORIES.slice(0, 6).map(c =>
    `<li><a href="${basePath}categories/${c.slug}.html">${c.name}</a></li>`
  ).join('');

  nav.innerHTML = `
    <div class="nav-inner">
      <a href="${basePath}index.html" class="nav-logo" aria-label="${SITE_NAME} home">
        <svg viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="2" y="2" width="24" height="24" rx="5" stroke="currentColor" stroke-width="2"/><circle cx="14" cy="11" r="4" stroke="currentColor" stroke-width="2"/><path d="M8 22c0-3.3 2.7-6 6-6s6 2.7 6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        ${SITE_NAME}
      </a>
      <ul class="nav-links">${catLinks}</ul>
      <button class="nav-toggle" aria-label="Toggle menu" aria-expanded="false">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
      </button>
    </div>
    <div class="nav-mobile" id="mobile-menu">
      <a href="${basePath}index.html"><strong>Home</strong></a>
      ${CATEGORIES.map(c => `<a href="${basePath}categories/${c.slug}.html">${c.icon} ${c.name}</a>`).join('')}
    </div>
  `;

  document.body.prepend(nav);

  const toggle = nav.querySelector('.nav-toggle');
  const menu = nav.querySelector('#mobile-menu');
  toggle.addEventListener('click', () => {
    const open = menu.classList.toggle('open');
    toggle.setAttribute('aria-expanded', open);
  });
}

/* ===== Footer ===== */
function renderFooter() {
  const isSubPage = window.location.pathname.includes('/tools/') || window.location.pathname.includes('/categories/');
  const basePath = isSubPage ? '../' : '';

  const footer = document.createElement('footer');
  footer.className = 'footer';
  footer.innerHTML = `
    <div class="footer-inner">
      <div class="footer-grid">
        <div>
          <h4>About</h4>
          <p>${SITE_NAME} is a curated AI tools directory operated by <strong>Machell Deals</strong>. We research, review, and compare AI products to help you find the right tool for your needs.</p>
          <p style="margin-top:0.5rem">Some links on this site are affiliate links. We may earn a commission at no extra cost to you.</p>
          <div class="footer-social" style="margin-top:0.75rem">
            <a href="https://t.me/dailydeals" target="_blank" rel="noopener" aria-label="Telegram">Telegram</a>
            <a href="https://x.com/MachellWil66296" target="_blank" rel="noopener" aria-label="X (Twitter)">X / Twitter</a>
          </div>
        </div>
        <div>
          <h4>Categories</h4>
          ${CATEGORIES.slice(0, 5).map(c => `<a href="${basePath}categories/${c.slug}.html">${c.name}</a>`).join('')}
        </div>
        <div>
          <h4>Top Tools</h4>
          ${TOOLS.slice(0, 5).map(t => `<a href="${basePath}tools/${t.slug}.html">${t.name}</a>`).join('')}
        </div>
        <div>
          <h4>Links</h4>
          <a href="${basePath}index.html">Home</a>
          <a href="${basePath}about.html">About Us</a>
          <a href="${basePath}contact.html">Contact</a>
          <a href="${basePath}privacy.html">Privacy Policy</a>
          <a href="${basePath}disclosure.html">Affiliate Disclosure</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; ${new Date().getFullYear()} ${SITE_NAME}. All rights reserved.</span>
        <span>Affiliate Disclosure: Some links earn us a commission at no cost to you.</span>
      </div>
    </div>
  `;
  document.body.appendChild(footer);
}

/* ===== Ad Slots ===== */
function initAds() {
  if (!ADSENSE_PUB_ID) return;
  document.querySelectorAll('.ad-slot').forEach(slot => {
    const format = slot.dataset.adFormat || 'auto';
    const adSlot = slot.dataset.adSlot || '';
    slot.innerHTML = `
      <ins class="adsbygoogle" style="display:block"
        data-ad-client="${ADSENSE_PUB_ID}"
        data-ad-slot="${adSlot}"
        data-ad-format="${format}"
        data-full-width-responsive="true"></ins>`;
    try { (adsbygoogle = window.adsbygoogle || []).push({}); } catch(e) {}
  });
}

/* ===== Tool Card HTML Generator ===== */
function toolCardHTML(tool, basePath) {
  const badgeClass = tool.pricing === 'free' ? 'badge-free' : tool.pricing === 'freemium' ? 'badge-freemium' : 'badge-paid';
  const badgeLabel = tool.pricing.charAt(0).toUpperCase() + tool.pricing.slice(1);
  const cat = CATEGORIES.find(c => c.slug === tool.category);
  return `
    <a href="${basePath}tools/${tool.slug}.html" class="tool-card">
      <div class="tool-card-header">
        <div class="tool-card-icon">${tool.icon}</div>
        <div>
          <h3>${tool.name}</h3>
        </div>
        <span class="tool-badge ${badgeClass}">${badgeLabel}</span>
      </div>
      <p>${tool.tagline}</p>
      <div class="tool-card-footer">
        <span class="tool-card-category">${cat ? cat.name : tool.category}</span>
        <span class="tool-card-rating">&#9733; ${tool.rating}</span>
      </div>
    </a>`;
}

/* ===== Search (homepage) ===== */
function initSearch() {
  const searchInput = document.getElementById('hero-search');
  const grid = document.getElementById('tool-grid');
  if (!searchInput || !grid) return;

  const isSubPage = window.location.pathname.includes('/tools/') || window.location.pathname.includes('/categories/');
  const basePath = isSubPage ? '../' : '';

  searchInput.addEventListener('input', () => {
    const q = searchInput.value.toLowerCase().trim();
    if (!q) {
      renderToolGrid(TOOLS, basePath);
      return;
    }
    const filtered = TOOLS.filter(t =>
      t.name.toLowerCase().includes(q) ||
      t.tagline.toLowerCase().includes(q) ||
      t.category.toLowerCase().includes(q) ||
      t.description.toLowerCase().includes(q)
    );
    renderToolGrid(filtered, basePath);
  });
}

function renderToolGrid(tools, basePath) {
  const grid = document.getElementById('tool-grid');
  if (!grid) return;
  if (tools.length === 0) {
    grid.innerHTML = '<p class="text-center text-muted" style="grid-column:1/-1;padding:2rem">No tools found matching your search.</p>';
    return;
  }
  grid.innerHTML = tools.map(t => toolCardHTML(t, basePath)).join('');
}

/* ===== Similar Tools ===== */
function renderSimilarTools(currentSlug) {
  const container = document.getElementById('similar-tools');
  if (!container) return;

  const isSubPage = window.location.pathname.includes('/tools/') || window.location.pathname.includes('/categories/');
  const basePath = isSubPage ? '../' : '';

  const current = TOOLS.find(t => t.slug === currentSlug);
  if (!current) return;

  const similar = TOOLS.filter(t => t.slug !== currentSlug && t.category === current.category).slice(0, 3);
  if (similar.length === 0) return;

  container.innerHTML = `
    <div class="section-heading"><h2>Similar Tools</h2></div>
    <div class="tool-grid">${similar.map(t => toolCardHTML(t, basePath)).join('')}</div>
  `;
}

/* ===== Init ===== */
document.addEventListener('DOMContentLoaded', () => {
  renderNav();
  renderFooter();
  initAds();
  initSearch();
});
