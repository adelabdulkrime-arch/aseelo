/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produces a minimal self-contained server bundle for the runtime image.
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
