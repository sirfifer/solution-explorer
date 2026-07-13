// Web client that calls the API service over HTTP.

export interface User {
  id: number;
  name: string;
}

const API_BASE = "http://api:8000";

export class ApiClient {
  private base: string;

  constructor(base: string = API_BASE) {
    this.base = base;
  }

  async getUser(id: number): Promise<User> {
    const res = await fetch(`${this.base}/users/${id}`);
    return (await res.json()) as User;
  }
}

export function createClient(): ApiClient {
  return new ApiClient();
}
