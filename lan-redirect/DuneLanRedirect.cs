// C# 5 (Windows PowerShell 5.1 Add-Type). Packet rewrite only. No payloads logged.
using System;
using System.Runtime.InteropServices;

public static class DuneLanRedirect
{
    public const int LayerNetwork = 0;
    public const int AddrLen = 80;
    public const int MaxPacket = 65535;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool SetDllDirectory(string lpPathName);

    [DllImport("WinDivert.dll", CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi, SetLastError = true)]
    public static extern IntPtr WinDivertOpen(string filter, int layer, short priority, ulong flags);

    [DllImport("WinDivert.dll", CallingConvention = CallingConvention.Cdecl, SetLastError = true)]
    public static extern bool WinDivertClose(IntPtr handle);

    [DllImport("WinDivert.dll", CallingConvention = CallingConvention.Cdecl, SetLastError = true)]
    public static extern bool WinDivertRecv(IntPtr handle, byte[] pPacket, uint packetLen, out uint recvLen, byte[] pAddr);

    [DllImport("WinDivert.dll", CallingConvention = CallingConvention.Cdecl, SetLastError = true)]
    public static extern bool WinDivertSend(IntPtr handle, byte[] pPacket, uint packetLen, out uint sendLen, byte[] pAddr);

    [DllImport("WinDivert.dll", CallingConvention = CallingConvention.Cdecl, SetLastError = true)]
    public static extern bool WinDivertHelperCalcChecksums(byte[] pPacket, uint packetLen, byte[] pAddr, ulong flags);

    public static int Verbose = 0;
    public static volatile bool Running = true;
    public static IntPtr Handle = IntPtr.Zero;

    public static void Log(string line, bool important)
    {
        if (Verbose > 0 || important)
            Console.WriteLine(line);
    }

    public static void RequestStop()
    {
        Running = false;
        if (Handle != IntPtr.Zero && Handle != new IntPtr(-1))
        {
            WinDivertClose(Handle);
            Handle = IntPtr.Zero;
        }
    }

    public static void StopOnCtrlC(object sender, ConsoleCancelEventArgs e)
    {
        e.Cancel = true;
        RequestStop();
    }

    public static byte[] ParseIpv4(string dotted)
    {
        string[] p = dotted.Split('.');
        if (p.Length != 4) throw new ArgumentException("need dotted IPv4");
        byte[] b = new byte[4];
        for (int i = 0; i < 4; i++)
        {
            int n = int.Parse(p[i]);
            if (n < 0 || n > 255) throw new ArgumentException("need dotted IPv4");
            b[i] = (byte)n;
        }
        return b;
    }

    public static bool IpEquals(byte[] packet, int offset, byte[] ip)
    {
        return packet[offset] == ip[0] && packet[offset + 1] == ip[1]
            && packet[offset + 2] == ip[2] && packet[offset + 3] == ip[3];
    }

    public static void SetIp(byte[] packet, int offset, byte[] ip)
    {
        packet[offset] = ip[0];
        packet[offset + 1] = ip[1];
        packet[offset + 2] = ip[2];
        packet[offset + 3] = ip[3];
    }

    public static bool IsDunePort(int port)
    {
        if (port >= 7777 && port <= 7810) return true;
        if (port >= 7888 && port <= 7941) return true;
        if (port == 31982 || port == 31519) return true;
        return false;
    }

    public static ushort ReadPort(byte[] packet, int offset)
    {
        return (ushort)((packet[offset] << 8) | packet[offset + 1]);
    }

    public static string FilterFor(string publicIp, string lanIp)
    {
        return
            "(outbound and ip.DstAddr == " + publicIp +
            " and ((udp and ((udp.DstPort >= 7777 and udp.DstPort <= 7810) or (udp.DstPort >= 7888 and udp.DstPort <= 7941))) or (tcp and (tcp.DstPort == 31982 or tcp.DstPort == 31519)))) or " +
            "(inbound and ip.SrcAddr == " + lanIp +
            " and ((udp and ((udp.SrcPort >= 7777 and udp.SrcPort <= 7810) or (udp.SrcPort >= 7888 and udp.SrcPort <= 7941))) or (tcp and (tcp.SrcPort == 31982 or tcp.SrcPort == 31519))))";
    }

    public static int Run(string dllDir, string publicIp, string lanIp, int verbose, bool bindCtrlC)
    {
        Verbose = verbose;
        byte[] pub = ParseIpv4(publicIp);
        byte[] lan = ParseIpv4(lanIp);
        if (IpEquals(pub, 0, lan))
        {
            Console.Error.WriteLine("Public and LAN IPs are the same. Nothing to rewrite.");
            return 2;
        }

        if (!SetDllDirectory(dllDir))
        {
            Console.Error.WriteLine("SetDllDirectory failed: " + Marshal.GetLastWin32Error());
            return 1;
        }

        string filter = FilterFor(publicIp, lanIp);
        Log("Filter: " + filter, false);
        IntPtr h = WinDivertOpen(filter, LayerNetwork, 0, 0);
        Handle = h;
        if (h == IntPtr.Zero || h == new IntPtr(-1))
        {
            int err = Marshal.GetLastWin32Error();
            Console.Error.WriteLine("WinDivertOpen failed (Win32 " + err + "). Need Administrator. If 577, the driver was blocked.");
            return 1;
        }

        if (bindCtrlC)
            Console.CancelKeyPress += StopOnCtrlC;

        Log("Rewriting " + publicIp + " <-> " + lanIp + " on Dune join/game ports.", true);
        if (Verbose > 0)
            Log("Leave this window open. Join from the Experimental list as usual. Ctrl+C to stop.", true);

        byte[] packet = new byte[MaxPacket];
        byte[] addr = new byte[AddrLen];
        uint recvLen, sendLen;
        int outCount = 0;
        int inCount = 0;

        try
        {
            while (Running)
            {
                recvLen = 0;
                if (!WinDivertRecv(h, packet, (uint)packet.Length, out recvLen, addr))
                {
                    int err = Marshal.GetLastWin32Error();
                    if (!Running) break;
                    if (err == 995) break;
                    Console.Error.WriteLine("WinDivertRecv " + err);
                    continue;
                }
                if (recvLen < 20) continue;
                int ver = packet[0] >> 4;
                if (ver != 4) continue;
                int ihl = (packet[0] & 0x0f) * 4;
                if (ihl < 20 || recvLen < ihl + 4) continue;
                int frag = ((packet[6] & 0x1f) << 8) | packet[7];
                if (frag != 0)
                {
                    WinDivertSend(h, packet, recvLen, out sendLen, addr);
                    continue;
                }
                int proto = packet[9];
                int dport = ReadPort(packet, ihl + 2);
                int sport = ReadPort(packet, ihl + 0);
                bool changed = false;
                if (IpEquals(packet, 16, pub) && IsDunePort(dport))
                {
                    SetIp(packet, 16, lan);
                    changed = true;
                    outCount++;
                    if (Verbose > 0 && (outCount == 1 || (outCount % 25) == 0))
                        Log("out x" + outCount + " proto=" + proto + " dport=" + dport, true);
                    else if (Verbose == 0 && outCount == 1)
                        Log("first rewrite out proto=" + proto + " dport=" + dport, true);
                }
                else if (IpEquals(packet, 12, lan) && IsDunePort(sport))
                {
                    SetIp(packet, 12, pub);
                    changed = true;
                    inCount++;
                    if (Verbose > 0 && (inCount == 1 || (inCount % 25) == 0))
                        Log("in  x" + inCount + " proto=" + proto + " sport=" + sport, true);
                    else if (Verbose == 0 && inCount == 1)
                        Log("first rewrite in proto=" + proto + " sport=" + sport, true);
                }
                if (changed)
                {
                    WinDivertHelperCalcChecksums(packet, recvLen, addr, 0);
                }
                if (!WinDivertSend(h, packet, recvLen, out sendLen, addr) && Running)
                {
                    Console.Error.WriteLine("WinDivertSend " + Marshal.GetLastWin32Error());
                }
            }
        }
        finally
        {
            if (Handle != IntPtr.Zero && Handle != new IntPtr(-1))
            {
                WinDivertClose(Handle);
                Handle = IntPtr.Zero;
            }
            Log("Stopped. out=" + outCount + " in=" + inCount, true);
        }
        return 0;
    }
}
