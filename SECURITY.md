# Security

## Supported versions

Only the newest release receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private
reporting instead: on the repository page, open the **Security** tab and choose
**Report a vulnerability**
(<https://github.com/AndyHoang/tvsend/security/advisories/new>).
If you cannot use GitHub, email ngocdunghoangdl@gmail.com instead.

Include the tvsend version, your operating system, and the steps that show the problem.
You can expect a first answer within a week.

## What is in scope

tvsend runs a small file server on your computer so the TV can fetch the video.
Reports about the following are especially welcome:

- the file server handing out a file that was not queued, or listening on more than
  the one network address facing the TV;
- the firewall help proposing a rule wider than the TV's address and the one port;
- the update command accepting a download whose checksum does not match;
- anything that lets another device on the network run commands or read files through
  tvsend.

## Good to know

- Traffic between the computer and the TV is plain HTTP on the home network; this is
  how DLNA works. Anyone on the same network who learns a clip's link can fetch that
  clip while it is queued.
- tvsend sends no telemetry. The only outside connection is the update check to GitHub.
