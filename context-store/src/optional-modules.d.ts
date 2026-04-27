// Ambient stubs so the optional peer-dep imports type-check without those
// packages being installed at our build time. The runtime adapters narrow
// the imports through their own local `unknown as ...` casts; these
// declarations exist purely to satisfy the module resolver.
//
// If a consumer installs the real package, node_modules takes precedence
// and these stubs are ignored.

declare module "redis" {
  const value: unknown;
  export = value;
}

declare module "mysql2/promise" {
  const value: unknown;
  export = value;
}

declare module "pg" {
  const value: unknown;
  export = value;
}

declare module "mongodb" {
  const value: unknown;
  export = value;
}
