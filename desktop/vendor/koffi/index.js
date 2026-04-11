"use strict";
var __getOwnPropNames = Object.getOwnPropertyNames;
var __commonJS = (cb, mod3) => function __require() {
  return mod3 || (0, cb[__getOwnPropNames(cb)[0]])((mod3 = { exports: {} }).exports, mod3), mod3.exports;
};

// package/src/cnoke/src/tools.js
var require_tools = __commonJS({
  "package/src/cnoke/src/tools.js"(exports2, module2) {
    "use strict";
    var crypto = require("crypto");
    var fs2 = require("fs");
    var http = require("https");
    var path2 = require("path");
    var zlib = require("zlib");
    async function download_http(url, dest) {
      console.log(">> Downloading " + url);
      let [tmp_name, file] = open_temporary_stream(dest);
      try {
        await new Promise((resolve, reject) => {
          let request = http.get(url, (response) => {
            if (response.statusCode != 200) {
              let err = new Error(`Download failed: ${response.statusMessage} [${response.statusCode}]`);
              err.code = response.statusCode;
              reject(err);
              return;
            }
            response.pipe(file);
            file.on("finish", () => file.close(() => {
              try {
                fs2.renameSync(file.path, dest);
              } catch (err) {
                if (!fs2.existsSync(dest))
                  reject(err);
              }
              resolve();
            }));
          });
          request.on("error", reject);
          file.on("error", reject);
        });
      } catch (err) {
        file.close();
        try {
          fs2.unlinkSync(tmp_name);
        } catch (err2) {
          if (err2.code != "ENOENT")
            throw err2;
        }
        throw err;
      }
    }
    function open_temporary_stream(prefix) {
      let buf = Buffer.allocUnsafe(4);
      for (; ; ) {
        try {
          crypto.randomFillSync(buf);
          let suffix = buf.toString("hex").padStart(8, "0");
          let filename2 = `${prefix}.${suffix}`;
          let file = fs2.createWriteStream(filename2, { flags: "wx", mode: 420 });
          return [filename2, file];
        } catch (err) {
          if (err.code != "EEXIST")
            throw err;
        }
      }
    }
    function extract_targz(filename2, dest_dir, strip = 0) {
      let reader = fs2.createReadStream(filename2).pipe(zlib.createGunzip());
      return new Promise((resolve, reject) => {
        let header = null;
        let extended = {};
        reader.on("readable", () => {
          try {
            for (; ; ) {
              if (header == null) {
                let buf = reader.read(512);
                if (buf == null)
                  break;
                if (!buf[0])
                  continue;
                header = {
                  filename: buf.toString("utf-8", 0, 100).replace(/\0/g, ""),
                  mode: parseInt(buf.toString("ascii", 100, 109), 8),
                  size: parseInt(buf.toString("ascii", 124, 137), 8),
                  type: String.fromCharCode(buf[156])
                };
                Object.assign(header, extended);
                extended = {};
                header.filename = header.filename.replace(/\\/g, "/");
                if (!header.filename.length)
                  throw new Error(`Insecure empty filename inside TAR archive`);
                if (path_is_absolute(header.filename[0]))
                  throw new Error(`Insecure filename starting with / inside TAR archive`);
                if (path_has_dotdot(header.filename))
                  throw new Error(`Insecure filename containing '..' inside TAR archive`);
                for (let i = 0; i < strip; i++)
                  header.filename = header.filename.substr(header.filename.indexOf("/") + 1);
              }
              let aligned = Math.floor((header.size + 511) / 512) * 512;
              let data = header.size ? reader.read(aligned) : null;
              if (data == null) {
                if (header.size)
                  break;
                data = Buffer.alloc(0);
              }
              data = data.subarray(0, header.size);
              if (header.type == "0" || header.type == "7") {
                let filename3 = dest_dir + "/" + header.filename;
                let dirname = path2.dirname(filename3);
                fs2.mkdirSync(dirname, { recursive: true, mode: 493 });
                fs2.writeFileSync(filename3, data, { mode: header.mode });
              } else if (header.type == "5") {
                let filename3 = dest_dir + "/" + header.filename;
                fs2.mkdirSync(filename3, { recursive: true, mode: header.mode });
              } else if (header.type == "L") {
                extended.filename = data.toString("utf-8").replace(/\0/g, "");
              } else if (header.type == "x") {
                let str = data.toString("utf-8");
                try {
                  while (str.length) {
                    let matches = str.match(/^([0-9]+) ([a-zA-Z0-9\._]+)=(.*)\n/);
                    let skip = parseInt(matches[1], 10);
                    let key = matches[2];
                    let value = matches[3];
                    switch (key) {
                      case "path":
                        {
                          extended.filename = value;
                        }
                        break;
                      case "size":
                        {
                          extended.size = parseInt(value, 10);
                        }
                        break;
                    }
                    str = str.substr(skip).trimStart();
                  }
                } catch (err) {
                  throw new Error("Malformed PAX entry");
                }
              }
              header = null;
            }
          } catch (err) {
            reject(err);
          }
        });
        reader.on("error", reject);
        reader.on("end", resolve);
      });
    }
    function path_is_absolute(path3) {
      if (process.platform == "win32" && path3.match(/^[a-zA-Z]:/))
        path3 = path3.substr(2);
      return is_path_separator(path3[0]);
    }
    function path_has_dotdot(path3) {
      let start = 0;
      for (; ; ) {
        let offset = path3.indexOf("..", start);
        if (offset < 0)
          break;
        start = offset + 2;
        if (offset && !is_path_separator(path3[offset - 1]))
          continue;
        if (offset + 2 < path3.length && !is_path_separator(path3[offset + 2]))
          continue;
        return true;
      }
      return false;
    }
    function is_path_separator(c) {
      if (c == "/")
        return true;
      if (process.platform == "win32" && c == "\\")
        return true;
      return false;
    }
    function sync_files(src_dir, dest_dir) {
      let keep = /* @__PURE__ */ new Set();
      {
        let entries = fs2.readdirSync(src_dir, { withFileTypes: true });
        for (let entry of entries) {
          if (!entry.isFile())
            continue;
          keep.add(entry.name);
          fs2.copyFileSync(src_dir + `/${entry.name}`, dest_dir + `/${entry.name}`);
        }
      }
      {
        let entries = fs2.readdirSync(dest_dir, { withFileTypes: true });
        for (let entry of entries) {
          if (!entry.isFile())
            continue;
          if (keep.has(entry.name))
            continue;
          fs2.unlinkSync(dest_dir + `/${entry.name}`);
        }
      }
    }
    function determine_arch2() {
      let arch = process.arch;
      if (arch == "riscv32" || arch == "riscv64") {
        let buf = read_file_header(process.execPath, 512);
        let header = decode_elf_header(buf);
        let float_abi = header.e_flags & 6;
        switch (float_abi) {
          case 0:
            {
            }
            break;
          case 2:
            {
              arch += "f";
            }
            break;
          case 4:
            {
              arch += "d";
            }
            break;
          case 6:
            {
              arch += "q";
            }
            break;
        }
      } else if (arch == "arm") {
        let buf = read_file_header(process.execPath, 512);
        let header = decode_elf_header(buf);
        if (header.e_flags & 1024) {
          arch += "hf";
        } else if (header.e_flags & 512) {
          arch += "sf";
        } else {
          throw new Error("Unknown ARM floating-point ABI");
        }
      }
      return arch;
    }
    function read_file_header(filename2, read) {
      let fd = null;
      try {
        let fd2 = fs2.openSync(filename2);
        let buf = Buffer.allocUnsafe(read);
        let len = fs2.readSync(fd2, buf);
        return buf.subarray(0, len);
      } finally {
        if (fd != null)
          fs2.closeSync(fd);
      }
    }
    function decode_elf_header(buf) {
      let header = {};
      if (buf.length < 16)
        throw new Error("Truncated header");
      if (buf[0] != 127 || buf[1] != 69 || buf[2] != 76 || buf[3] != 70)
        throw new Error("Invalid magic number");
      if (buf[6] != 1)
        throw new Error("Invalid ELF version");
      if (buf[5] != 1)
        throw new Error("Big-endian architectures are not supported");
      let machine = buf.readUInt16LE(18);
      switch (machine) {
        case 3:
          {
            header.e_machine = "ia32";
          }
          break;
        case 40:
          {
            header.e_machine = "arm";
          }
          break;
        case 62:
          {
            header.e_machine = "amd64";
          }
          break;
        case 183:
          {
            header.e_machine = "arm64";
          }
          break;
        case 243:
          {
            switch (buf[4]) {
              case 1:
                {
                  header.e_machine = "riscv32";
                }
                break;
              case 2:
                {
                  header.e_machine = "riscv64";
                }
                break;
            }
          }
          break;
        case 248:
          {
            switch (buf[4]) {
              case 1:
                {
                  header.e_machine = "loong32";
                }
                break;
              case 2:
                {
                  header.e_machine = "loong64";
                }
                break;
            }
          }
          break;
        default:
          throw new Error("Unknown ELF machine type");
      }
      switch (buf[4]) {
        case 1:
          {
            buf = buf.subarray(0, 68);
            if (buf.length < 68)
              throw new Error("Truncated ELF header");
            header.ei_class = 32;
            header.e_flags = buf.readUInt32LE(36);
          }
          break;
        case 2:
          {
            buf = buf.subarray(0, 120);
            if (buf.length < 120)
              throw new Error("Truncated ELF header");
            header.ei_class = 64;
            header.e_flags = buf.readUInt32LE(48);
          }
          break;
        default:
          throw new Error("Invalid ELF class");
      }
      return header;
    }
    function unlink_recursive(path3) {
      try {
        fs2.rmSync(path3, { recursive: true, maxRetries: process.platform == "win32" ? 3 : 0 });
      } catch (err) {
        if (err.code !== "ENOENT")
          throw err;
      }
    }
    function get_napi_version2(napi, major) {
      if (napi > 8)
        return null;
      const support = {
        6: ["6.14.2", "6.14.2", "6.14.2"],
        8: ["8.6.0", "8.10.0", "8.11.2"],
        9: ["9.0.0", "9.3.0", "9.11.0"],
        10: ["10.0.0", "10.0.0", "10.0.0", "10.16.0", "10.17.0", "10.20.0", "10.23.0"],
        11: ["11.0.0", "11.0.0", "11.0.0", "11.8.0"],
        12: ["12.0.0", "12.0.0", "12.0.0", "12.0.0", "12.11.0", "12.17.0", "12.19.0", "12.22.0"],
        13: ["13.0.0", "13.0.0", "13.0.0", "13.0.0", "13.0.0"],
        14: ["14.0.0", "14.0.0", "14.0.0", "14.0.0", "14.0.0", "14.0.0", "14.12.0", "14.17.0"],
        15: ["15.0.0", "15.0.0", "15.0.0", "15.0.0", "15.0.0", "15.0.0", "15.0.0", "15.12.0"]
      };
      const max = Math.max(...Object.keys(support).map((k) => parseInt(k, 10)));
      if (major > max)
        return major + ".0.0";
      if (support[major] == null)
        return null;
      let required = support[major][napi - 1] || null;
      return required;
    }
    function cmp_version(ver1, ver2) {
      ver1 = String(ver1).replace(/-.*$/, "").split(".").reduce((acc, v, idx) => acc + parseInt(v, 10) * Math.pow(10, 2 * (5 - idx)), 0);
      ver2 = String(ver2).replace(/-.*$/, "").split(".").reduce((acc, v, idx) => acc + parseInt(v, 10) * Math.pow(10, 2 * (5 - idx)), 0);
      let cmp = Math.min(Math.max(ver1 - ver2, -1), 1);
      return cmp;
    }
    module2.exports = {
      download_http,
      extract_targz,
      path_is_absolute,
      path_has_dotdot,
      sync_files,
      determine_arch: determine_arch2,
      unlink_recursive,
      get_napi_version: get_napi_version2,
      cmp_version
    };
  }
});

// package/src/koffi/package.json
var require_package = __commonJS({
  "package/src/koffi/package.json"(exports2, module2) {
    module2.exports = {
      name: "koffi",
      version: "2.15.2",
      description: "Fast and simple C FFI (foreign function interface) for Node.js",
      keywords: [
        "foreign",
        "function",
        "interface",
        "ffi",
        "binding",
        "c",
        "napi"
      ],
      repository: {
        type: "git",
        url: "https://github.com/Koromix/koffi"
      },
      homepage: "https://koffi.dev/",
      author: {
        name: "Niels Martign\xE8ne",
        email: "niels.martignene@protonmail.com",
        url: "https://koromix.dev/"
      },
      main: "./index.js",
      types: "./index.d.ts",
      scripts: {
        test: "node tools/koffi.js test",
        prepack: `echo 'Use "npm run package" instead' && false`,
        prepublishOnly: `echo 'Use "npm run package" instead' && false`,
        package: "node tools/koffi.js build"
      },
      license: "MIT",
      cnoke: {
        api: "../../vendor/node-api-headers",
        output: "../../bin/Koffi/{{ toolchain }}",
        node: 16,
        napi: 8,
        require: "./index.js"
      },
      funding: "https://liberapay.com/Koromix"
    };
  }
});

// package/src/koffi/src/init.js
var require_init = __commonJS({
  "package/src/koffi/src/init.js"(exports, module) {
    var fs = require("fs");
    var path = require("path");
    var util = require("util");
    var { get_napi_version, determine_arch } = require_tools();
    var pkg = require_package();
    function detect() {
      if (process.versions.napi == null || process.versions.napi < pkg.cnoke.napi) {
        let major = parseInt(process.versions.node, 10);
        let required = get_napi_version(pkg.cnoke.napi, major);
        if (required != null) {
          throw new Error(`This engine is based on Node ${process.versions.node}, but ${pkg.name} requires Node >= ${required} in the Node ${major}.x branch (N-API >= ${pkg.cnoke.napi})`);
        } else {
          throw new Error(`This engine is based on Node ${process.versions.node}, but ${pkg.name} does not support the Node ${major}.x branch (N-API < ${pkg.cnoke.napi})`);
        }
      }
      let arch = determine_arch();
      let triplet3 = `${process.platform}_${arch}`;
      return triplet3;
    }
    function init(triplet, native) {
      if (native == null) {
        let roots = [path.join(__dirname, "..")];
        let triplets = [triplet];
        if (process.resourcesPath != null)
          roots.push(process.resourcesPath);
        if (triplet.startsWith("linux_")) {
          let musl = triplet.replace(/^linux_/, "musl_");
          triplets.push(musl);
        }
        let filenames = roots.flatMap((root) => triplets.flatMap((triplet3) => [
          `${root}/koffi/build/koffi/${triplet3}/koffi.node`,
          `${root}/build/koffi/${triplet3}/koffi.node`,
          `${root}/koffi/${triplet3}/koffi.node`,
          `${root}/node_modules/koffi/build/koffi/${triplet3}/koffi.node`,
          `${root}/../../bin/Koffi/${triplet3}/koffi.node`
        ]));
        let first_err = null;
        for (let filename of filenames) {
          if (!fs.existsSync(filename))
            continue;
          try {
            native = eval("require")(filename);
          } catch (err) {
            if (first_err == null)
              first_err = err;
            continue;
          }
          break;
        }
        if (first_err != null)
          throw first_err;
      }
      if (native == null)
        throw new Error("Cannot find the native Koffi module; did you bundle it correctly?");
      if (native.version != pkg.version)
        throw new Error("Mismatched native Koffi modules");
      let mod = wrap(native);
      return mod;
    }
    function wrap(native3) {
      let obj = {
        ...native3,
        // Deprecated functions
        handle: util.deprecate(native3.opaque, "The koffi.handle() function was deprecated in Koffi 2.1, use koffi.opaque() instead", "KOFFI001"),
        callback: util.deprecate(native3.proto, "The koffi.callback() function was deprecated in Koffi 2.4, use koffi.proto() instead", "KOFFI002")
      };
      obj.load = (...args) => {
        let lib = native3.load(...args);
        lib.cdecl = util.deprecate((...args2) => lib.func("__cdecl", ...args2), "The koffi.cdecl() function was deprecated in Koffi 2.7, use koffi.func(...) instead", "KOFFI003");
        lib.stdcall = util.deprecate((...args2) => lib.func("__stdcall", ...args2), 'The koffi.stdcall() function was deprecated in Koffi 2.7, use koffi.func("__stdcall", ...) instead', "KOFFI004");
        lib.fastcall = util.deprecate((...args2) => lib.func("__fastcall", ...args2), 'The koffi.fastcall() function was deprecated in Koffi 2.7, use koffi.func("__fastcall", ...) instead', "KOFFI005");
        lib.thiscall = util.deprecate((...args2) => lib.func("__thiscall", ...args2), 'The koffi.thiscall() function was deprecated in Koffi 2.7, use koffi.func("__thiscall", ...) instead', "KOFFI006");
        return lib;
      };
      return obj;
    }
    module.exports = {
      detect,
      init
    };
  }
});

// package/src/koffi/index.js
var { detect: detect2, init: init2 } = require_init();
var triplet2 = detect2();
var native2 = null;
try {
  switch (triplet2) {
    case "darwin_arm64":
      {
        native2 = require("./build/koffi/darwin_arm64/koffi.node");
      }
      break;
    case "darwin_x64":
      {
        native2 = require("./build/koffi/darwin_x64/koffi.node");
      }
      break;
    case "freebsd_arm64":
      {
        native2 = require("./build/koffi/freebsd_arm64/koffi.node");
      }
      break;
    case "freebsd_ia32":
      {
        native2 = require("./build/koffi/freebsd_ia32/koffi.node");
      }
      break;
    case "freebsd_x64":
      {
        native2 = require("./build/koffi/freebsd_x64/koffi.node");
      }
      break;
    case "linux_armhf":
      {
        native2 = require("./build/koffi/linux_armhf/koffi.node");
      }
      break;
    case "linux_arm64":
      {
        native2 = require("./build/koffi/linux_arm64/koffi.node");
      }
      break;
    case "linux_ia32":
      {
        native2 = require("./build/koffi/linux_ia32/koffi.node");
      }
      break;
    case "linux_loong64":
      {
        native2 = require("./build/koffi/linux_loong64/koffi.node");
      }
      break;
    case "linux_riscv64d":
      {
        native2 = require("./build/koffi/linux_riscv64d/koffi.node");
      }
      break;
    case "linux_x64":
      {
        native2 = require("./build/koffi/linux_x64/koffi.node");
      }
      break;
    case "openbsd_ia32":
      {
        native2 = require("./build/koffi/openbsd_ia32/koffi.node");
      }
      break;
    case "openbsd_x64":
      {
        native2 = require("./build/koffi/openbsd_x64/koffi.node");
      }
      break;
    case "win32_arm64":
      {
        native2 = require("./build/koffi/win32_arm64/koffi.node");
      }
      break;
    case "win32_ia32":
      {
        native2 = require("./build/koffi/win32_ia32/koffi.node");
      }
      break;
    case "win32_x64":
      {
        native2 = require("./build/koffi/win32_x64/koffi.node");
      }
      break;
  }
} catch {
  try {
    switch (triplet2) {
      case "linux_arm64":
        {
          native2 = require("./build/koffi/musl_arm64/koffi.node");
        }
        break;
      case "linux_x64":
        {
          native2 = require("./build/koffi/musl_x64/koffi.node");
        }
        break;
    }
  } catch {
  }
}
var mod2 = init2(triplet2, native2);
module.exports = mod2;
