import { ProductDetail, ProductListItem } from "./types";

const baseUrl = process.env.API_BASE_URL ?? "http://api:8000";

export async function fetchProducts(searchParams?: Record<string, string | string[] | undefined>): Promise<ProductListItem[]> {
  const query = new URLSearchParams();
  Object.entries(searchParams ?? {}).forEach(([key, value]) => {
    if (!value) {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => query.append(key, item));
      return;
    }
    query.set(key, value);
  });
  const response = await fetch(`${baseUrl}/products${query.size ? `?${query.toString()}` : ""}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load products");
  }
  return response.json();
}

export async function fetchProductDetail(skuId: string): Promise<ProductDetail> {
  const response = await fetch(`${baseUrl}/products/${skuId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load product");
  }
  return response.json();
}
