#include <arpa/inet.h>
#include <csignal>
#include <errno.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

namespace fs = std::filesystem;

static volatile sig_atomic_t g_should_exit = 0;

static void handle_sigint(int) { g_should_exit = 1; }

struct HttpRequest {
  std::string method;
  std::string path;
  std::map<std::string, std::string> headers;
  std::string body;
};

static std::string to_lower(std::string s) {
  for (auto &ch : s) ch = static_cast<char>(::tolower(static_cast<unsigned char>(ch)));
  return s;
}

static std::string trim(std::string s) {
  auto is_ws = [](unsigned char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; };
  while (!s.empty() && is_ws(static_cast<unsigned char>(s.front()))) s.erase(s.begin());
  while (!s.empty() && is_ws(static_cast<unsigned char>(s.back()))) s.pop_back();
  return s;
}

static bool read_exact(int fd, void *buf, size_t n) {
  char *out = static_cast<char *>(buf);
  size_t got = 0;
  while (got < n) {
    ssize_t r = ::recv(fd, out + got, n - got, 0);
    if (r == 0) return false;
    if (r < 0) {
      if (errno == EINTR) continue;
      return false;
    }
    got += static_cast<size_t>(r);
  }
  return true;
}

static bool read_headers(int fd, std::string &headers, std::string &rest, size_t max_bytes = 1024 * 1024) {
  headers.clear();
  rest.clear();
  std::string buf;
  buf.reserve(8192);
  while (buf.size() < max_bytes) {
    char chunk[4096];
    ssize_t r = ::recv(fd, chunk, sizeof(chunk), 0);
    if (r == 0) return false;
    if (r < 0) {
      if (errno == EINTR) continue;
      return false;
    }
    buf.append(chunk, static_cast<size_t>(r));
    auto pos = buf.find("\r\n\r\n");
    if (pos != std::string::npos) {
      headers = buf.substr(0, pos + 4);
      rest = buf.substr(pos + 4);
      return true;
    }
  }
  return false;
}

static std::optional<HttpRequest> parse_request(int fd) {
  std::string header_blob;
  std::string rest;
  if (!read_headers(fd, header_blob, rest)) {
    return std::nullopt;
  }

  std::istringstream iss(header_blob);
  std::string request_line;
  if (!std::getline(iss, request_line)) return std::nullopt;
  request_line = trim(request_line);

  HttpRequest req;
  {
    std::istringstream rl(request_line);
    rl >> req.method;
    rl >> req.path;
    if (req.method.empty() || req.path.empty()) return std::nullopt;
  }

  std::string line;
  while (std::getline(iss, line)) {
    line = trim(line);
    if (line.empty()) break;
    auto colon = line.find(':');
    if (colon == std::string::npos) continue;
    std::string key = to_lower(trim(line.substr(0, colon)));
    std::string value = trim(line.substr(colon + 1));
    req.headers[key] = value;
  }

  size_t content_len = 0;
  auto it = req.headers.find("content-length");
  if (it != req.headers.end()) {
    try {
      content_len = static_cast<size_t>(std::stoul(it->second));
    } catch (...) {
      content_len = 0;
    }
  }
  if (content_len > 0) {
    req.body = rest;
    if (req.body.size() > content_len) req.body.resize(content_len);
    if (req.body.size() < content_len) {
      const size_t remaining = content_len - req.body.size();
      const size_t offset = req.body.size();
      req.body.resize(content_len);
      if (!read_exact(fd, req.body.data() + offset, remaining)) {
        return std::nullopt;
      }
    }
  }
  return req;
}

static bool write_all(int fd, const void *buf, size_t n) {
  const char *in = static_cast<const char *>(buf);
  size_t sent = 0;
  while (sent < n) {
    ssize_t w = ::send(fd, in + sent, n - sent, 0);
    if (w < 0) {
      if (errno == EINTR) continue;
      return false;
    }
    sent += static_cast<size_t>(w);
  }
  return true;
}

static void send_json(int fd, int code, const std::string &payload) {
  std::ostringstream oss;
  oss << "HTTP/1.1 " << code << " OK\r\n"
      << "Content-Type: application/json\r\n"
      << "Content-Length: " << payload.size() << "\r\n"
      << "Connection: close\r\n\r\n"
      << payload;
  auto blob = oss.str();
  write_all(fd, blob.data(), blob.size());
}

static void send_bytes(int fd, int code, const std::string &content_type, const std::vector<unsigned char> &bytes) {
  std::ostringstream oss;
  oss << "HTTP/1.1 " << code << " OK\r\n"
      << "Content-Type: " << content_type << "\r\n"
      << "Content-Length: " << bytes.size() << "\r\n"
      << "Connection: close\r\n\r\n";
  auto header = oss.str();
  write_all(fd, header.data(), header.size());
  if (!bytes.empty()) {
    write_all(fd, bytes.data(), bytes.size());
  }
}

static std::optional<std::string> json_get_string(std::string_view body, std::string_view key) {
  const std::string needle = "\"" + std::string(key) + "\"";
  size_t pos = body.find(needle);
  if (pos == std::string_view::npos) return std::nullopt;
  pos = body.find(':', pos + needle.size());
  if (pos == std::string_view::npos) return std::nullopt;
  pos++;
  while (pos < body.size() && (body[pos] == ' ' || body[pos] == '\t' || body[pos] == '\r' || body[pos] == '\n'))
    pos++;
  if (pos >= body.size() || body[pos] != '"') return std::nullopt;
  pos++;
  std::string out;
  out.reserve(256);
  while (pos < body.size()) {
    char c = body[pos++];
    if (c == '"') break;
    if (c == '\\' && pos < body.size()) {
      char e = body[pos++];
      switch (e) {
        case '"': out.push_back('"'); break;
        case '\\': out.push_back('\\'); break;
        case '/': out.push_back('/'); break;
        case 'b': out.push_back('\b'); break;
        case 'f': out.push_back('\f'); break;
        case 'n': out.push_back('\n'); break;
        case 'r': out.push_back('\r'); break;
        case 't': out.push_back('\t'); break;
        case 'u': {
          for (int i = 0; i < 4 && pos < body.size(); i++) pos++;
          out.push_back('?');
          break;
        }
        default:
          out.push_back(e);
      }
    } else {
      out.push_back(c);
    }
  }
  return out;
}

static std::vector<unsigned char> read_file_bytes(const fs::path &path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) return {};
  std::vector<unsigned char> buf;
  in.seekg(0, std::ios::end);
  auto size = in.tellg();
  if (size <= 0) return {};
  buf.resize(static_cast<size_t>(size));
  in.seekg(0, std::ios::beg);
  in.read(reinterpret_cast<char *>(buf.data()), static_cast<std::streamsize>(buf.size()));
  return buf;
}

static int run_infer(
    const fs::path &infer_script,
    const fs::path &model_dir,
    const std::string &text,
    const fs::path &output,
    const std::string &voice_reference,
    const std::string &language) {
  std::vector<std::string> argv;
  argv.push_back("python3");
  argv.push_back(infer_script.string());
  argv.push_back("--model-dir");
  argv.push_back(model_dir.string());
  argv.push_back("--text");
  argv.push_back(text);
  argv.push_back("--output");
  argv.push_back(output.string());
  if (!voice_reference.empty()) {
    argv.push_back("--voice-reference");
    argv.push_back(voice_reference);
  }
  if (!language.empty()) {
    argv.push_back("--language");
    argv.push_back(language);
  }

  std::vector<char *> c_argv;
  c_argv.reserve(argv.size() + 1);
  for (auto &item : argv) c_argv.push_back(item.data());
  c_argv.push_back(nullptr);

  pid_t pid = fork();
  if (pid < 0) return 1;
  if (pid == 0) {
    execvp(c_argv[0], c_argv.data());
    _exit(127);
  }
  int status = 0;
  while (waitpid(pid, &status, 0) < 0) {
    if (errno == EINTR) continue;
    return 1;
  }
  if (WIFEXITED(status)) return WEXITSTATUS(status);
  return 1;
}

static void usage(const char *argv0) {
  std::cerr << "Usage: " << argv0 << " --host 127.0.0.1 --port 8890 --model-dir /path/to/pockettts\n"
            << "       [--default-language auto]\n";
}

int main(int argc, char **argv) {
  std::string host = "127.0.0.1";
  int port = 8890;
  fs::path model_dir;
  std::string default_language = "auto";

  for (int i = 1; i < argc; i++) {
    std::string arg = argv[i];
    auto next = [&]() -> std::optional<std::string> {
      if (i + 1 >= argc) return std::nullopt;
      return std::string(argv[++i]);
    };
    if (arg == "--host") {
      auto v = next();
      if (!v) { usage(argv[0]); return 2; }
      host = *v;
    } else if (arg == "--port") {
      auto v = next();
      if (!v) { usage(argv[0]); return 2; }
      port = std::atoi(v->c_str());
    } else if (arg == "--model-dir") {
      auto v = next();
      if (!v) { usage(argv[0]); return 2; }
      model_dir = fs::path(*v);
    } else if (arg == "--default-language") {
      auto v = next();
      if (!v) { usage(argv[0]); return 2; }
      default_language = *v;
    } else if (arg == "-h" || arg == "--help") {
      usage(argv[0]);
      return 0;
    }
  }

  if (model_dir.empty()) {
    usage(argv[0]);
    return 2;
  }

  std::signal(SIGINT, handle_sigint);
  std::signal(SIGTERM, handle_sigint);

  int server_fd = ::socket(AF_INET, SOCK_STREAM, 0);
  if (server_fd < 0) {
    std::perror("socket");
    return 1;
  }
  int opt = 1;
  setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(static_cast<uint16_t>(port));
  if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) <= 0) {
    std::cerr << "Invalid host address: " << host << "\n";
    return 2;
  }
  if (::bind(server_fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) < 0) {
    std::perror("bind");
    return 1;
  }
  if (::listen(server_fd, 32) < 0) {
    std::perror("listen");
    return 1;
  }

  const fs::path infer_script = fs::absolute(fs::path(argv[0]).parent_path() / "pockettts_infer.py");
  if (!fs::exists(infer_script)) {
    std::cerr << "Missing infer script next to the server binary: " << infer_script << "\n";
    return 2;
  }

  std::cerr << "PocketTTS server listening on " << host << ":" << port << "\n";
  while (!g_should_exit) {
    sockaddr_in client{};
    socklen_t client_len = sizeof(client);
    int client_fd = ::accept(server_fd, reinterpret_cast<sockaddr *>(&client), &client_len);
    if (client_fd < 0) {
      if (errno == EINTR) continue;
      std::perror("accept");
      break;
    }

    auto maybe = parse_request(client_fd);
    if (!maybe) {
      ::close(client_fd);
      continue;
    }
    const HttpRequest &req = *maybe;

    if (req.method == "GET" && req.path == "/health") {
      send_json(client_fd, 200, "{\"ok\":true}");
      ::close(client_fd);
      continue;
    }
    if (req.method == "GET" && req.path == "/v1/models") {
      send_json(client_fd, 200, "{\"data\":[{\"id\":\"pockettts-local\"}]}");
      ::close(client_fd);
      continue;
    }
    if (req.method == "POST" && req.path == "/v1/audio/speech") {
      auto input = json_get_string(req.body, "input").value_or("");
      if (input.empty()) {
        send_json(client_fd, 400, "{\"error\":\"input is required\"}");
        ::close(client_fd);
        continue;
      }
      auto voice_ref = json_get_string(req.body, "voice_reference").value_or("");
      auto language = json_get_string(req.body, "language").value_or(default_language);

      fs::path tmp_dir = fs::temp_directory_path() / "hanauta-pockettts";
      std::error_code ec;
      fs::create_directories(tmp_dir, ec);
      fs::path out_wav = tmp_dir / ("out_" + std::to_string(::getpid()) + "_" + std::to_string(std::rand()) + ".wav");

      int rc = run_infer(infer_script, model_dir, input, out_wav, voice_ref, language);
      if (rc != 0) {
        send_json(client_fd, 500, "{\"error\":\"PocketTTS inference failed\"}");
        ::close(client_fd);
        std::error_code ignore;
        fs::remove(out_wav, ignore);
        continue;
      }
      auto bytes = read_file_bytes(out_wav);
      std::error_code ignore;
      fs::remove(out_wav, ignore);
      if (bytes.empty()) {
        send_json(client_fd, 500, "{\"error\":\"PocketTTS returned empty audio\"}");
        ::close(client_fd);
        continue;
      }
      send_bytes(client_fd, 200, "audio/wav", bytes);
      ::close(client_fd);
      continue;
    }

    send_json(client_fd, 404, "{\"error\":\"not found\"}");
    ::close(client_fd);
  }

  ::close(server_fd);
  return 0;
}
