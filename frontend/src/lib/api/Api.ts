/* eslint-disable */
/* tslint:disable */
// @ts-nocheck
/*
 * ---------------------------------------------------------------
 * ## THIS FILE WAS GENERATED VIA SWAGGER-TYPESCRIPT-API        ##
 * ##                                                           ##
 * ## AUTHOR: acacode                                           ##
 * ## SOURCE: https://github.com/acacode/swagger-typescript-api ##
 * ---------------------------------------------------------------
 */

/** ServerStatus */
export enum ServerStatus {
  Online = "online",
  Offline = "offline",
  Unknown = "unknown",
}

/** QueryProtocol */
export enum QueryProtocol {
  MinecraftJava = "minecraft_java",
  MinecraftBedrock = "minecraft_bedrock",
  A2S = "a2s",
  FactorioRcon = "factorio_rcon",
  SatisfactoryApi = "satisfactory_api",
  ArkEos = "ark_eos",
}

/** GameServerType */
export enum GameServerType {
  Minecraft = "minecraft",
  MinecraftBedrock = "minecraft_bedrock",
  Factorio = "factorio",
  Satisfactory = "satisfactory",
  ArkAse = "ark_ase",
  ArkAsa = "ark_asa",
  Valheim = "valheim",
  Rust = "rust",
  SevenDaysToDie = "seven_days_to_die",
  Palworld = "palworld",
  ProjectZomboid = "project_zomboid",
  Enshrouded = "enshrouded",
  VRising = "v_rising",
  ConanExiles = "conan_exiles",
  Dayz = "dayz",
  CounterStrike = "counter_strike",
  TeamFortress2 = "team_fortress_2",
  GarrysMod = "garrys_mod",
  Unturned = "unturned",
  Steam = "steam",
}

/**
 * ArkServerInfo
 * ARK-specific server information (Survival Evolved and Survival Ascended).
 */
export interface ArkServerInfo {
  /**
   * Kind
   * @default "ark"
   */
  kind?: "ark";
  status: ServerStatus;
  /** Latency */
  latency?: number | null;
  /** Version */
  version?: string | null;
  /** Server Name */
  server_name?: string | null;
  /** Description */
  description?: string | null;
  /** Icon */
  icon?: string | null;
  /** Mods */
  mods?: Record<string, any>[] | null;
  /** Game Mode */
  game_mode?: string | null;
  /** Map Name */
  map_name?: string | null;
  /** Password Protected */
  password_protected?: boolean | null;
  /** Anti Cheat Enabled */
  anti_cheat_enabled?: boolean | null;
  /** Players Online */
  players_online?: number | null;
  /** Players Max */
  players_max?: number | null;
  /** Player List */
  player_list?: string[] | null;
  /** Error Message */
  error_message?: string | null;
  /** Day Time */
  day_time?: string | null;
  /** Official */
  official?: boolean | null;
  /** Pve */
  pve?: boolean | null;
  /** Cluster Id */
  cluster_id?: string | null;
  /** Platform Type */
  platform_type?: string | null;
}

/**
 * BaseServerInfo
 * Base model for live server information that all game servers should provide.
 */
export interface BaseServerInfo {
  /**
   * Kind
   * @default "base"
   */
  kind?: "base";
  status: ServerStatus;
  /** Latency */
  latency?: number | null;
  /** Version */
  version?: string | null;
  /** Server Name */
  server_name?: string | null;
  /** Description */
  description?: string | null;
  /** Icon */
  icon?: string | null;
  /** Mods */
  mods?: Record<string, any>[] | null;
  /** Game Mode */
  game_mode?: string | null;
  /** Map Name */
  map_name?: string | null;
  /** Password Protected */
  password_protected?: boolean | null;
  /** Anti Cheat Enabled */
  anti_cheat_enabled?: boolean | null;
  /** Players Online */
  players_online?: number | null;
  /** Players Max */
  players_max?: number | null;
  /** Player List */
  player_list?: string[] | null;
  /** Error Message */
  error_message?: string | null;
}

/** ContainerInfo */
export interface ContainerInfo {
  /** Name */
  name: string;
  /** Image */
  image: string;
  /** State */
  state: string;
  /** Ports */
  ports: PortBinding[];
}

/**
 * FactorioServerInfo
 * Factorio-specific server information (fetched via RCON).
 */
export interface FactorioServerInfo {
  /**
   * Kind
   * @default "factorio"
   */
  kind?: "factorio";
  status: ServerStatus;
  /** Latency */
  latency?: number | null;
  /** Version */
  version?: string | null;
  /** Server Name */
  server_name?: string | null;
  /** Description */
  description?: string | null;
  /** Icon */
  icon?: string | null;
  /** Mods */
  mods?: Record<string, any>[] | null;
  /** Game Mode */
  game_mode?: string | null;
  /** Map Name */
  map_name?: string | null;
  /** Password Protected */
  password_protected?: boolean | null;
  /** Anti Cheat Enabled */
  anti_cheat_enabled?: boolean | null;
  /** Players Online */
  players_online?: number | null;
  /** Players Max */
  players_max?: number | null;
  /** Player List */
  player_list?: string[] | null;
  /** Error Message */
  error_message?: string | null;
  /** Tags */
  tags?: string[] | null;
  /** Public */
  public?: boolean | null;
  /** Require User Verification */
  require_user_verification?: boolean | null;
  /** Allow Commands */
  allow_commands?: string | null;
  /** Game Time */
  game_time?: string | null;
  /** Evolution */
  evolution?: Record<string, number> | null;
  /** Seed */
  seed?: string | null;
}

/** GameServerCreate */
export interface GameServerCreate {
  /** Name */
  name: string;
  game: GameServerType;
  /** Address */
  address: string;
  /**
   * Port
   * @min 1
   * @max 65535
   */
  port: number;
  /** Query Port */
  query_port?: number | null;
  /** Rcon Port */
  rcon_port?: number | null;
  /** Rcon Password */
  rcon_password?: string | null;
}

/**
 * GameServerPublic
 * API representation of a server: everything except secrets.
 */
export interface GameServerPublic {
  game: GameServerType;
  /**
   * Name
   * @maxLength 100
   */
  name: string;
  /**
   * Address
   * @maxLength 100
   */
  address: string;
  /**
   * Port
   * @min 1
   * @max 65535
   */
  port: number;
  /** Query Port */
  query_port?: number | null;
  /** Rcon Port */
  rcon_port?: number | null;
  /** Id */
  id: string;
  /**
   * Has Rcon
   * @default false
   */
  has_rcon?: boolean;
}

/** GameServerUpdate */
export interface GameServerUpdate {
  /** Name */
  name?: string | null;
  game?: GameServerType | null;
  /** Address */
  address?: string | null;
  /** Port */
  port?: number | null;
  /** Query Port */
  query_port?: number | null;
  /** Rcon Port */
  rcon_port?: number | null;
  /** Rcon Password */
  rcon_password?: string | null;
}

/** GameTypeInfo */
export interface GameTypeInfo {
  type: GameServerType;
  /** Label */
  label: string;
  protocol: QueryProtocol;
  /** Default Port */
  default_port: number;
  /** Default Query Port */
  default_query_port: number | null;
  /** Default Rcon Port */
  default_rcon_port: number | null;
  /** Needs Rcon */
  needs_rcon: boolean;
}

/** HTTPValidationError */
export interface HTTPValidationError {
  /** Detail */
  detail?: ValidationError[];
}

/** LoginRequest */
export interface LoginRequest {
  /** Username */
  username: string;
  /** Password */
  password: string;
}

/** LoginResponse */
export interface LoginResponse {
  /** Token */
  token: string;
  /** Username */
  username: string;
  /** Expires At */
  expires_at: number;
}

/**
 * MinecraftServerInfo
 * Minecraft-specific server information (Java and Bedrock editions).
 */
export interface MinecraftServerInfo {
  /**
   * Kind
   * @default "minecraft"
   */
  kind?: "minecraft";
  status: ServerStatus;
  /** Latency */
  latency?: number | null;
  /** Version */
  version?: string | null;
  /** Server Name */
  server_name?: string | null;
  /** Description */
  description?: string | null;
  /** Icon */
  icon?: string | null;
  /** Mods */
  mods?: Record<string, any>[] | null;
  /** Game Mode */
  game_mode?: string | null;
  /** Map Name */
  map_name?: string | null;
  /** Password Protected */
  password_protected?: boolean | null;
  /** Anti Cheat Enabled */
  anti_cheat_enabled?: boolean | null;
  /** Players Online */
  players_online?: number | null;
  /** Players Max */
  players_max?: number | null;
  /** Player List */
  player_list?: string[] | null;
  /** Error Message */
  error_message?: string | null;
  /** Edition */
  edition?: string | null;
  /** Protocol */
  protocol?: number | null;
  /** Enforces Secure Chat */
  enforces_secure_chat?: boolean | null;
}

/** PortBinding */
export interface PortBinding {
  /** Host Port */
  host_port: number;
  /** Protocol */
  protocol: string;
}

/**
 * SatisfactoryServerInfo
 * Satisfactory-specific server information.
 */
export interface SatisfactoryServerInfo {
  /**
   * Kind
   * @default "satisfactory"
   */
  kind?: "satisfactory";
  status: ServerStatus;
  /** Latency */
  latency?: number | null;
  /** Version */
  version?: string | null;
  /** Server Name */
  server_name?: string | null;
  /** Description */
  description?: string | null;
  /** Icon */
  icon?: string | null;
  /** Mods */
  mods?: Record<string, any>[] | null;
  /** Game Mode */
  game_mode?: string | null;
  /** Map Name */
  map_name?: string | null;
  /** Password Protected */
  password_protected?: boolean | null;
  /** Anti Cheat Enabled */
  anti_cheat_enabled?: boolean | null;
  /** Players Online */
  players_online?: number | null;
  /** Players Max */
  players_max?: number | null;
  /** Player List */
  player_list?: string[] | null;
  /** Error Message */
  error_message?: string | null;
  /** Session Name */
  session_name?: string | null;
  /** Tech Tier */
  tech_tier?: number | null;
  /** Game Phase */
  game_phase?: string | null;
  /** Total Game Duration */
  total_game_duration?: number | null;
  /** Avg Tick Rate */
  avg_tick_rate?: number | null;
  /** Is Paused */
  is_paused?: boolean | null;
}

/** SessionInfo */
export interface SessionInfo {
  /** Auth Enabled */
  auth_enabled: boolean;
  /** Username */
  username?: string | null;
}

/**
 * SteamServerInfo
 * Generic Steam / Source engine (A2S) server information.
 */
export interface SteamServerInfo {
  /**
   * Kind
   * @default "steam"
   */
  kind?: "steam";
  status: ServerStatus;
  /** Latency */
  latency?: number | null;
  /** Version */
  version?: string | null;
  /** Server Name */
  server_name?: string | null;
  /** Description */
  description?: string | null;
  /** Icon */
  icon?: string | null;
  /** Mods */
  mods?: Record<string, any>[] | null;
  /** Game Mode */
  game_mode?: string | null;
  /** Map Name */
  map_name?: string | null;
  /** Password Protected */
  password_protected?: boolean | null;
  /** Anti Cheat Enabled */
  anti_cheat_enabled?: boolean | null;
  /** Players Online */
  players_online?: number | null;
  /** Players Max */
  players_max?: number | null;
  /** Player List */
  player_list?: string[] | null;
  /** Error Message */
  error_message?: string | null;
  /** Game */
  game?: string | null;
  /** App Id */
  app_id?: number | null;
  /** Folder */
  folder?: string | null;
  /** Protocol */
  protocol?: number | null;
  /** Bot Count */
  bot_count?: number | null;
  /** Server Type */
  server_type?: string | null;
  /** Platform */
  platform?: string | null;
  /** Keywords */
  keywords?: string | null;
  /** Rules */
  rules?: Record<string, string> | null;
}

/** ValidationError */
export interface ValidationError {
  /** Location */
  loc: (string | number)[];
  /** Message */
  msg: string;
  /** Error Type */
  type: string;
  /** Input */
  input?: any;
  /** Context */
  ctx?: object;
}

export type QueryParamsType = Record<string | number, any>;
export type ResponseFormat = keyof Omit<Body, "body" | "bodyUsed">;

export interface FullRequestParams extends Omit<RequestInit, "body"> {
  /** set parameter to `true` for call `securityWorker` for this request */
  secure?: boolean;
  /** request path */
  path: string;
  /** content type of request body */
  type?: ContentType;
  /** query params */
  query?: QueryParamsType;
  /** format of response (i.e. response.json() -> format: "json") */
  format?: ResponseFormat;
  /** request body */
  body?: unknown;
  /** base url */
  baseUrl?: string;
  /** request cancellation token */
  cancelToken?: CancelToken;
}

export type RequestParams = Omit<
  FullRequestParams,
  "body" | "method" | "query" | "path"
>;

export interface ApiConfig<SecurityDataType = unknown> {
  baseUrl?: string;
  baseApiParams?: Omit<RequestParams, "baseUrl" | "cancelToken" | "signal">;
  securityWorker?: (
    securityData: SecurityDataType | null,
  ) => Promise<RequestParams | void> | RequestParams | void;
  customFetch?: typeof fetch;
}

export interface HttpResponse<D extends unknown, E extends unknown = unknown>
  extends Response {
  data: D;
  error: E;
}

type CancelToken = Symbol | string | number;

export enum ContentType {
  Json = "application/json",
  JsonApi = "application/vnd.api+json",
  FormData = "multipart/form-data",
  UrlEncoded = "application/x-www-form-urlencoded",
  Text = "text/plain",
}

export class HttpClient<SecurityDataType = unknown> {
  public baseUrl: string = "";
  private securityData: SecurityDataType | null = null;
  private securityWorker?: ApiConfig<SecurityDataType>["securityWorker"];
  private abortControllers = new Map<CancelToken, AbortController>();
  private customFetch = (...fetchParams: Parameters<typeof fetch>) =>
    fetch(...fetchParams);

  private baseApiParams: RequestParams = {
    credentials: "same-origin",
    headers: {},
    redirect: "follow",
    referrerPolicy: "no-referrer",
  };

  constructor(apiConfig: ApiConfig<SecurityDataType> = {}) {
    Object.assign(this, apiConfig);
  }

  public setSecurityData = (data: SecurityDataType | null) => {
    this.securityData = data;
  };

  protected encodeQueryParam(key: string, value: any) {
    const encodedKey = encodeURIComponent(key);
    return `${encodedKey}=${encodeURIComponent(typeof value === "number" ? value : `${value}`)}`;
  }

  protected addQueryParam(query: QueryParamsType, key: string) {
    return this.encodeQueryParam(key, query[key]);
  }

  protected addArrayQueryParam(query: QueryParamsType, key: string) {
    const value = query[key];
    return value.map((v: any) => this.encodeQueryParam(key, v)).join("&");
  }

  protected toQueryString(rawQuery?: QueryParamsType): string {
    const query = rawQuery || {};
    const keys = Object.keys(query).filter(
      (key) => "undefined" !== typeof query[key],
    );
    return keys
      .map((key) =>
        Array.isArray(query[key])
          ? this.addArrayQueryParam(query, key)
          : this.addQueryParam(query, key),
      )
      .join("&");
  }

  protected addQueryParams(rawQuery?: QueryParamsType): string {
    const queryString = this.toQueryString(rawQuery);
    return queryString ? `?${queryString}` : "";
  }

  private contentFormatters: Record<ContentType, (input: any) => any> = {
    [ContentType.Json]: (input: any) =>
      input !== null && (typeof input === "object" || typeof input === "string")
        ? JSON.stringify(input)
        : input,
    [ContentType.JsonApi]: (input: any) =>
      input !== null && (typeof input === "object" || typeof input === "string")
        ? JSON.stringify(input)
        : input,
    [ContentType.Text]: (input: any) =>
      input !== null && typeof input !== "string"
        ? JSON.stringify(input)
        : input,
    [ContentType.FormData]: (input: any) => {
      if (input instanceof FormData) {
        return input;
      }

      return Object.keys(input || {}).reduce((formData, key) => {
        const property = input[key];
        formData.append(
          key,
          property instanceof Blob
            ? property
            : typeof property === "object" && property !== null
              ? JSON.stringify(property)
              : `${property}`,
        );
        return formData;
      }, new FormData());
    },
    [ContentType.UrlEncoded]: (input: any) => this.toQueryString(input),
  };

  protected mergeRequestParams(
    params1: RequestParams,
    params2?: RequestParams,
  ): RequestParams {
    return {
      ...this.baseApiParams,
      ...params1,
      ...(params2 || {}),
      headers: {
        ...(this.baseApiParams.headers || {}),
        ...(params1.headers || {}),
        ...((params2 && params2.headers) || {}),
      },
    };
  }

  protected createAbortSignal = (
    cancelToken: CancelToken,
  ): AbortSignal | undefined => {
    if (this.abortControllers.has(cancelToken)) {
      const abortController = this.abortControllers.get(cancelToken);
      if (abortController) {
        return abortController.signal;
      }
      return void 0;
    }

    const abortController = new AbortController();
    this.abortControllers.set(cancelToken, abortController);
    return abortController.signal;
  };

  public abortRequest = (cancelToken: CancelToken) => {
    const abortController = this.abortControllers.get(cancelToken);

    if (abortController) {
      abortController.abort();
      this.abortControllers.delete(cancelToken);
    }
  };

  public request = async <T = any, E = any>({
    body,
    secure,
    path,
    type,
    query,
    format,
    baseUrl,
    cancelToken,
    ...params
  }: FullRequestParams): Promise<HttpResponse<T, E>> => {
    const secureParams =
      ((typeof secure === "boolean" ? secure : this.baseApiParams.secure) &&
        this.securityWorker &&
        (await this.securityWorker(this.securityData))) ||
      {};
    const requestParams = this.mergeRequestParams(params, secureParams);
    const queryString = query && this.toQueryString(query);
    const payloadFormatter = this.contentFormatters[type || ContentType.Json];
    const responseFormat = format || requestParams.format;

    return this.customFetch(
      `${baseUrl || this.baseUrl || ""}${path}${queryString ? `?${queryString}` : ""}`,
      {
        ...requestParams,
        headers: {
          ...(requestParams.headers || {}),
          ...(type && type !== ContentType.FormData
            ? { "Content-Type": type }
            : {}),
        },
        signal:
          (cancelToken
            ? this.createAbortSignal(cancelToken)
            : requestParams.signal) || null,
        body:
          typeof body === "undefined" || body === null
            ? null
            : payloadFormatter(body),
      },
    ).then(async (response) => {
      const r = response as HttpResponse<T, E>;
      r.data = null as unknown as T;
      r.error = null as unknown as E;

      const responseToParse = responseFormat ? response.clone() : response;
      const data = !responseFormat
        ? r
        : await responseToParse[responseFormat]()
            .then((data) => {
              if (r.ok) {
                r.data = data;
              } else {
                r.error = data;
              }
              return r;
            })
            .catch((e) => {
              r.error = e;
              return r;
            });

      if (cancelToken) {
        this.abortControllers.delete(cancelToken);
      }

      if (!response.ok) throw data;
      return data;
    });
  };
}

/**
 * @title Game Server Dashboard API
 * @version 0.6.0
 *
 * API for managing and monitoring game servers
 */
export class Api<
  SecurityDataType extends unknown,
> extends HttpClient<SecurityDataType> {
  /**
   * @description Get all game servers from the database.
   *
   * @tags servers
   * @name GetServers
   * @summary Get Servers
   * @request GET:/api/servers
   * @secure
   */
  getServers = (params: RequestParams = {}) =>
    this.request<GameServerPublic[], any>({
      path: `/api/servers`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });

  /**
   * @description Create a new game server.
   *
   * @tags servers
   * @name PostServer
   * @summary Post Server
   * @request POST:/api/servers
   * @secure
   */
  postServer = (data: GameServerCreate, params: RequestParams = {}) =>
    this.request<GameServerPublic, HTTPValidationError>({
      path: `/api/servers`,
      method: "POST",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });

  /**
   * No description
   *
   * @name RootGet
   * @summary Root
   * @request GET:/
   */
  rootGet = (params: RequestParams = {}) =>
    this.request<any, any>({
      path: `/`,
      method: "GET",
      format: "json",
      ...params,
    });

  login = {
    /**
     * @description Exchange username and password for a bearer token.
     *
     * @tags auth
     * @name Login
     * @summary Login
     * @request POST:/api/auth/login
     */
    login: (data: LoginRequest, params: RequestParams = {}) =>
      this.request<LoginResponse, HTTPValidationError>({
        path: `/api/auth/login`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),
  };
  me = {
    /**
     * @description Whether login is required and who the caller is. Returns 401 for a missing or expired token.
     *
     * @tags auth
     * @name GetSession
     * @summary Me
     * @request GET:/api/auth/me
     * @secure
     */
    getSession: (params: RequestParams = {}) =>
      this.request<SessionInfo, any>({
        path: `/api/auth/me`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),
  };
  supportedTypes = {
    /**
     * @description Get list of supported game server types.
     *
     * @tags servers
     * @name GetSupportedServerTypes
     * @summary Supported Types
     * @request GET:/api/servers/supported_types
     * @secure
     */
    getSupportedServerTypes: (params: RequestParams = {}) =>
      this.request<GameServerType[], any>({
        path: `/api/servers/supported_types`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),
  };
  gameTypes = {
    /**
     * @description Get supported game types with display labels and default ports (for forms).
     *
     * @tags servers
     * @name GetGameTypes
     * @summary Game Types
     * @request GET:/api/servers/game-types
     * @secure
     */
    getGameTypes: (params: RequestParams = {}) =>
      this.request<GameTypeInfo[], any>({
        path: `/api/servers/game-types`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),
  };
  liveInfo = {
    /**
     * @description Get live information for every server at once (queried concurrently).
     *
     * @tags servers
     * @name GetAllServersLiveInfo
     * @summary Get All Servers Live Info
     * @request GET:/api/servers/live-info
     * @secure
     */
    getAllServersLiveInfo: (params: RequestParams = {}) =>
      this.request<
        Record<
          string,
          | ({
              kind: "base";
            } & BaseServerInfo)
          | ({
              kind: "steam";
            } & SteamServerInfo)
          | ({
              kind: "minecraft";
            } & MinecraftServerInfo)
          | ({
              kind: "factorio";
            } & FactorioServerInfo)
          | ({
              kind: "satisfactory";
            } & SatisfactoryServerInfo)
          | ({
              kind: "ark";
            } & ArkServerInfo)
        >,
        any
      >({
        path: `/api/servers/live-info`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),
  };
  byType = {
    /**
     * @description Get all servers of a specific game type.
     *
     * @tags servers
     * @name GetServersByType
     * @summary Get Servers By Type
     * @request GET:/api/servers/by-type/{server_type}
     * @secure
     */
    getServersByType: (
      serverType: GameServerType,
      params: RequestParams = {},
    ) =>
      this.request<GameServerPublic[], HTTPValidationError>({
        path: `/api/servers/by-type/${serverType}`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),
  };
  serverId = {
    /**
     * @description Get a specific game server by ID.
     *
     * @tags servers
     * @name GetServerById
     * @summary Get Server
     * @request GET:/api/servers/{server_id}
     * @secure
     */
    getServerById: (serverId: string, params: RequestParams = {}) =>
      this.request<GameServerPublic, HTTPValidationError>({
        path: `/api/servers/${serverId}`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),

    /**
     * @description Update an existing game server (only fields that are sent are changed).
     *
     * @tags servers
     * @name UpdateServer
     * @summary Update Server
     * @request PUT:/api/servers/{server_id}
     * @secure
     */
    updateServer: (
      serverId: string,
      data: GameServerUpdate,
      params: RequestParams = {},
    ) =>
      this.request<GameServerPublic, HTTPValidationError>({
        path: `/api/servers/${serverId}`,
        method: "PUT",
        body: data,
        secure: true,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * @description Delete a game server.
     *
     * @tags servers
     * @name DeleteServer
     * @summary Delete Server
     * @request DELETE:/api/servers/{server_id}
     * @secure
     */
    deleteServer: (serverId: string, params: RequestParams = {}) =>
      this.request<any, HTTPValidationError>({
        path: `/api/servers/${serverId}`,
        method: "DELETE",
        secure: true,
        format: "json",
        ...params,
      }),

    /**
     * @description Get live information for a server by its database ID.
     *
     * @tags servers
     * @name GetServerLiveInfoById
     * @summary Get Server Live Info By Id
     * @request GET:/api/servers/{server_id}/live-info
     * @secure
     */
    getServerLiveInfoById: (serverId: string, params: RequestParams = {}) =>
      this.request<
        | ({
            kind: "base";
          } & BaseServerInfo)
        | ({
            kind: "steam";
          } & SteamServerInfo)
        | ({
            kind: "minecraft";
          } & MinecraftServerInfo)
        | ({
            kind: "factorio";
          } & FactorioServerInfo)
        | ({
            kind: "satisfactory";
          } & SatisfactoryServerInfo)
        | ({
            kind: "ark";
          } & ArkServerInfo),
        HTTPValidationError
      >({
        path: `/api/servers/${serverId}/live-info`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),
  };
  containers = {
    /**
     * @description List every container on the host regardless of state.
     *
     * @tags docker
     * @name ListAllContainersApiDockerContainersGet
     * @summary List All Containers
     * @request GET:/api/docker/containers
     * @secure
     */
    listAllContainersApiDockerContainersGet: (params: RequestParams = {}) =>
      this.request<ContainerInfo[], any>({
        path: `/api/docker/containers`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),

    /**
     * @description List only containers labelled gamefleet.managed=true.
     *
     * @tags docker
     * @name ListManagedContainersApiDockerContainersManagedGet
     * @summary List Managed Containers
     * @request GET:/api/docker/containers/managed
     * @secure
     */
    listManagedContainersApiDockerContainersManagedGet: (
      params: RequestParams = {},
    ) =>
      this.request<ContainerInfo[], any>({
        path: `/api/docker/containers/managed`,
        method: "GET",
        secure: true,
        format: "json",
        ...params,
      }),
  };
  game = {
    /**
     * @description Serve cached game artwork: `poster` (portrait) or `hero` (wide banner).
     *
     * @tags games
     * @name GetGameAsset
     * @summary Get Game Asset
     * @request GET:/api/games/{game}/{kind}
     */
    getGameAsset: (
      game: GameServerType,
      kind: string,
      params: RequestParams = {},
    ) =>
      this.request<void, HTTPValidationError>({
        path: `/api/games/${game}/${kind}`,
        method: "GET",
        ...params,
      }),
  };
}
