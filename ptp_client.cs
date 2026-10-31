using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace OpenEOS.Ptp
{
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct PROPERTYKEY
    {
        public Guid fmtid;
        public uint pid;

        public PROPERTYKEY(Guid fmtid, uint pid)
        {
            this.fmtid = fmtid;
            this.pid = pid;
        }
    }

    [StructLayout(LayoutKind.Explicit)]
    public struct PROPVARIANT
    {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(2)] public ushort wReserved1;
        [FieldOffset(4)] public ushort wReserved2;
        [FieldOffset(6)] public ushort wReserved3;
        [FieldOffset(8)] public uint uintVal;
        [FieldOffset(8)] public IntPtr ptrVal;
    }

    [ComImport]
    [Guid("0c15d803-d329-476b-bd73-4d56047c8730")]
    public class PortableDeviceValuesClass { }

    [ComImport]
    [Guid("688262e3-887c-4700-9d1e-bc15199f45ce")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPortableDeviceValues
    {
        void Initialize();
        void GetCount(out uint pcProperties);
        void GetAt(uint index, ref PROPERTYKEY pKey, out PROPVARIANT pValue);
        void SetValue(ref PROPERTYKEY key, ref PROPVARIANT pValue);
        void GetStringValue(ref PROPERTYKEY key, [MarshalAs(UnmanagedType.LPWStr)] out string pValue);
        void SetStringValue(ref PROPERTYKEY key, [MarshalAs(UnmanagedType.LPWStr)] string pValue);
        void GetUnsignedIntegerValue(ref PROPERTYKEY key, out uint pValue);
        void SetUnsignedIntegerValue(ref PROPERTYKEY key, uint pValue);
        void GetSignedIntegerValue(ref PROPERTYKEY key, out int pValue);
        void SetSignedIntegerValue(ref PROPERTYKEY key, int pValue);
        void GetUnsignedLargeIntegerValue(ref PROPERTYKEY key, out ulong pValue);
        void SetUnsignedLargeIntegerValue(ref PROPERTYKEY key, ulong pValue);
        void GetSignedLargeIntegerValue(ref PROPERTYKEY key, out long pValue);
        void SetSignedLargeIntegerValue(ref PROPERTYKEY key, long pValue);
        void GetFloatValue(ref PROPERTYKEY key, out float pValue);
        void SetFloatValue(ref PROPERTYKEY key, float pValue);
        void GetErrorValue(ref PROPERTYKEY key, out int pValue);
        void SetErrorValue(ref PROPERTYKEY key, int pValue);
        void GetKeyValue(ref PROPERTYKEY key, out PROPERTYKEY pValue);
        void SetKeyValue(ref PROPERTYKEY key, ref PROPERTYKEY pValue);
        void GetBoolValue(ref PROPERTYKEY key, out int pValue);
        void SetBoolValue(ref PROPERTYKEY key, int pValue);
        void GetIUnknownValue(ref PROPERTYKEY key, [MarshalAs(UnmanagedType.IUnknown)] out object ppUnk);
        void SetIUnknownValue(ref PROPERTYKEY key, [MarshalAs(UnmanagedType.IUnknown)] object pUnk);
        void GetGuidValue(ref PROPERTYKEY key, out Guid pValue);
        void SetGuidValue(ref PROPERTYKEY key, ref Guid pValue);
        void GetBufferValue(ref PROPERTYKEY key, out IntPtr ppBuffer, out uint pcbBuffer);
        void SetBufferValue(ref PROPERTYKEY key, IntPtr pBuffer, uint cbBuffer);
        void GetIPortableDeviceValuesValue(ref PROPERTYKEY key, out IPortableDeviceValues ppValue);
        void SetIPortableDeviceValuesValue(ref PROPERTYKEY key, IPortableDeviceValues pValue);
        void GetIPortableDevicePropVariantCollectionValue(ref PROPERTYKEY key, out IPortableDevicePropVariantCollection ppValue);
        void SetIPortableDevicePropVariantCollectionValue(ref PROPERTYKEY key, IPortableDevicePropVariantCollection pValue);
        void GetIPortableDeviceKeyCollectionValue(ref PROPERTYKEY key, out IntPtr ppValue);
        void SetIPortableDeviceKeyCollectionValue(ref PROPERTYKEY key, IntPtr pValue);
        void GetIPortableDeviceValuesCollectionValue(ref PROPERTYKEY key, out IntPtr ppValue);
        void SetIPortableDeviceValuesCollectionValue(ref PROPERTYKEY key, IntPtr pValue);
        void RemoveValue(ref PROPERTYKEY key);
        void CopyValuesFromPropertyStore(IntPtr pStore);
        void CopyValuesToPropertyStore(IntPtr pStore);
        void Clear();
    }

    [ComImport]
    [Guid("81062c28-479c-4059-8679-ced40d00fa74")]
    public class PortableDeviceClass { }

    [ComImport]
    [Guid("625e2df1-2924-47a2-bf11-484fb95d94e1")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPortableDevice
    {
        void Open([MarshalAs(UnmanagedType.LPWStr)] string pszPnPDeviceID, IPortableDeviceValues pClientInformation);
        void SendCommand(uint dwFlags, IPortableDeviceValues pParameters, out IPortableDeviceValues ppResults);
        void Close();
        void Capabilities(out IntPtr ppCapabilities);
        void Content(out IntPtr ppContent);
        void Advise(uint dwFlags, IntPtr pCallback, IPortableDeviceValues pParameters, [MarshalAs(UnmanagedType.LPWStr)] out string ppszCookie);
        void Unadvise([MarshalAs(UnmanagedType.LPWStr)] string pszCookie);
    }

    [ComImport]
    [Guid("0af10cec-2ecd-4b92-9581-34f6754d1210")]
    public class PortableDeviceManagerClass { }

    [ComImport]
    [Guid("a1567595-4c2f-4574-a6fa-ecef917b9a40")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPortableDeviceManager
    {
        void GetDevices(IntPtr pPnpDeviceIDs, ref uint pcPnpDeviceIDs);
        void RefreshDeviceList();
        void GetDeviceManufacturer([MarshalAs(UnmanagedType.LPWStr)] string pPnpDeviceID, [Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pDeviceManufacturer, ref uint pcDeviceManufacturer);
        void GetDeviceDescription([MarshalAs(UnmanagedType.LPWStr)] string pPnpDeviceID, [Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pDeviceDescription, ref uint pcDeviceDescription);
        void GetDeviceFriendlyName([MarshalAs(UnmanagedType.LPWStr)] string pPnpDeviceID, [Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pDeviceFriendlyName, ref uint pcDeviceFriendlyName);
        void GetDeviceProperty([MarshalAs(UnmanagedType.LPWStr)] string pPnpDeviceID, [MarshalAs(UnmanagedType.LPWStr)] string pProperty, IntPtr pData, ref uint pcbData, ref uint pdwType);
        void GetPrivateDevices(IntPtr pPnpDeviceIDs, ref uint pcPnpDeviceIDs);
    }

    [ComImport]
    [Guid("08a14e2a-c3b2-477d-a664-508f9d6b7940")]
    public class PortableDevicePropVariantCollectionClass { }

    [ComImport]
    [Guid("89e2c49f-3503-470b-9d94-4888653b8135")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPortableDevicePropVariantCollection
    {
        void GetCount(out uint pcElems);
        void GetAt(uint dwIndex, out PROPVARIANT pValue);
        void Add(ref PROPVARIANT pValue);
        void Clear();
        void ChangeType(ushort vt);
    }

    public class PtpDeviceInfo
    {
        public ushort StandardVersion;
        public uint VendorExtensionId;
        public ushort VendorExtensionVersion;
        public string VendorExtensionDesc;
        public ushort FunctionalMode;
        public List<ushort> OperationsSupported = new List<ushort>();
        public List<ushort> EventsSupported = new List<ushort>();
        public List<ushort> DevicePropertiesSupported = new List<ushort>();
        public List<ushort> CaptureFormats = new List<ushort>();
        public List<ushort> ImageFormats = new List<ushort>();
        public string Manufacturer;
        public string Model;
        public string DeviceVersion;
        public string SerialNumber;

        public static PtpDeviceInfo Parse(byte[] data)
        {
            int offset = 0;
            PtpDeviceInfo info = new PtpDeviceInfo();
            if (data == null || data.Length < 14) return info;

            info.StandardVersion = BitConverter.ToUInt16(data, offset); offset += 2;
            info.VendorExtensionId = BitConverter.ToUInt32(data, offset); offset += 4;
            info.VendorExtensionVersion = BitConverter.ToUInt16(data, offset); offset += 2;
            info.VendorExtensionDesc = ReadPtpString(data, ref offset);
            if (offset + 2 <= data.Length)
            {
                info.FunctionalMode = BitConverter.ToUInt16(data, offset); offset += 2;
            }

            info.OperationsSupported = ReadPtpArray(data, ref offset);
            info.EventsSupported = ReadPtpArray(data, ref offset);
            info.DevicePropertiesSupported = ReadPtpArray(data, ref offset);
            info.CaptureFormats = ReadPtpArray(data, ref offset);
            info.ImageFormats = ReadPtpArray(data, ref offset);

            info.Manufacturer = ReadPtpString(data, ref offset);
            info.Model = ReadPtpString(data, ref offset);
            info.DeviceVersion = ReadPtpString(data, ref offset);
            info.SerialNumber = ReadPtpString(data, ref offset);

            return info;
        }

        private static string ReadPtpString(byte[] data, ref int offset)
        {
            if (offset >= data.Length) return "";
            byte len = data[offset++];
            if (len == 0) return "";
            int byteLen = (len - 1) * 2;
            if (byteLen < 0) byteLen = 0;
            if (offset + byteLen > data.Length) byteLen = data.Length - offset;
            string s = Encoding.Unicode.GetString(data, offset, byteLen);
            offset += len * 2;
            return s;
        }

        private static List<ushort> ReadPtpArray(byte[] data, ref int offset)
        {
            List<ushort> list = new List<ushort>();
            if (offset + 4 > data.Length) return list;
            uint count = BitConverter.ToUInt32(data, offset); offset += 4;
            for (int i = 0; i < count && offset + 2 <= data.Length; i++)
            {
                list.Add(BitConverter.ToUInt16(data, offset));
                offset += 2;
            }
            return list;
        }
    }

    public class Program
    {
        static Guid WPD_COMMAND_MTP_EXT = new Guid("4D545058-AE60-4789-FF00-000000000000");
        static PROPERTYKEY WPD_PROPERTY_COMMON_COMMAND_CATEGORY = new PROPERTYKEY(new Guid("F0422A9C-5DC8-4440-B5BD-5DF38D4001FA"), 1001);
        static PROPERTYKEY WPD_PROPERTY_COMMON_COMMAND_ID = new PROPERTYKEY(new Guid("F0422A9C-5DC8-4440-B5BD-5DF38D4001FA"), 1002);

        static PROPERTYKEY WPD_PROPERTY_MTP_EXT_OPERATION_CODE = new PROPERTYKEY(new Guid("4D545058-AE60-4789-FF00-000000000000"), 1001);
        static PROPERTYKEY WPD_PROPERTY_MTP_EXT_OPERATION_PARAMS = new PROPERTYKEY(new Guid("4D545058-AE60-4789-FF00-000000000000"), 1002);
        static PROPERTYKEY WPD_PROPERTY_MTP_EXT_RESPONSE_CODE = new PROPERTYKEY(new Guid("4D545058-AE60-4789-FF00-000000000000"), 1003);
        static PROPERTYKEY WPD_PROPERTY_MTP_EXT_TRANSFER_CONTEXT = new PROPERTYKEY(new Guid("4D545058-AE60-4789-FF00-000000000000"), 1006);
        static PROPERTYKEY WPD_PROPERTY_MTP_EXT_BYTES_TO_READ = new PROPERTYKEY(new Guid("4D545058-AE60-4789-FF00-000000000000"), 1007);
        static PROPERTYKEY WPD_PROPERTY_MTP_EXT_DATA = new PROPERTYKEY(new Guid("4D545058-AE60-4789-FF00-000000000000"), 1008);

        static PROPERTYKEY WPD_CLIENT_NAME = new PROPERTYKEY(new Guid("204D9840-22EA-4E05-93B2-F6A34BF56C4C"), 2);
        static PROPERTYKEY WPD_CLIENT_MAJOR_VERSION = new PROPERTYKEY(new Guid("204D9840-22EA-4E05-93B2-F6A34BF56C4C"), 3);
        static PROPERTYKEY WPD_CLIENT_MINOR_VERSION = new PROPERTYKEY(new Guid("204D9840-22EA-4E05-93B2-F6A34BF56C4C"), 4);

        static List<string> logLines = new List<string>();

        static void Log(string msg = "")
        {
            Console.WriteLine(msg);
            logLines.Add(msg);
        }

        static string FindCanonDeviceId()
        {
            // Метод 1: Через COM IPortableDeviceManager
            try
            {
                IPortableDeviceManager mgr = (IPortableDeviceManager)new PortableDeviceManagerClass();
                uint count = 0;
                mgr.GetDevices(IntPtr.Zero, ref count);

                if (count > 0)
                {
                    IntPtr[] ptrs = new IntPtr[count];
                    GCHandle h = GCHandle.Alloc(ptrs, GCHandleType.Pinned);
                    try
                    {
                        mgr.GetDevices(h.AddrOfPinnedObject(), ref count);
                    }
                    finally
                    {
                        h.Free();
                    }

                    for (int i = 0; i < count; i++)
                    {
                        if (ptrs[i] == IntPtr.Zero) continue;
                        string id = Marshal.PtrToStringUni(ptrs[i]);
                        Marshal.FreeCoTaskMem(ptrs[i]);

                        if (string.IsNullOrEmpty(id)) continue;

                        uint nameLen = 256;
                        StringBuilder sbName = new StringBuilder((int)nameLen);
                        try { mgr.GetDeviceFriendlyName(id, sbName, ref nameLen); } catch { }
                        string name = sbName.ToString();

                        if (name.IndexOf("Canon", StringComparison.OrdinalIgnoreCase) >= 0 ||
                            id.IndexOf("VID_04A9", StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            return id;
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Log("    [*] Поиск через IPortableDeviceManager: " + ex.Message);
            }

            // Метод 2: Резервный поиск через реестр Windows Enum (WpdMtpDriver SymbolicLink)
            try
            {
                using (RegistryKey baseKey = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Enum\USB"))
                {
                    if (baseKey != null)
                    {
                        foreach (string subName in baseKey.GetSubKeyNames())
                        {
                            if (subName.IndexOf("VID_04A9", StringComparison.OrdinalIgnoreCase) >= 0 &&
                                subName.IndexOf("MI_00", StringComparison.OrdinalIgnoreCase) >= 0)
                            {
                                using (RegistryKey devKey = baseKey.OpenSubKey(subName))
                                {
                                    if (devKey == null) continue;
                                    foreach (string instName in devKey.GetSubKeyNames())
                                    {
                                        using (RegistryKey pKey = devKey.OpenSubKey(instName + @"\Device Parameters\WpdMtpDriver"))
                                        {
                                            if (pKey != null)
                                            {
                                                object sym = pKey.GetValue("SymbolicLink");
                                                if (sym != null)
                                                {
                                                    return sym.ToString();
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            catch { }

            return null;
        }

        static byte[] ExecuteMtpCommandWithDataToRead(IPortableDevice device, ushort opCode, uint[] parameters)
        {
            IPortableDeviceValues cmdParams = (IPortableDeviceValues)new PortableDeviceValuesClass();
            Guid cat = WPD_COMMAND_MTP_EXT;
            cmdParams.SetGuidValue(ref WPD_PROPERTY_COMMON_COMMAND_CATEGORY, ref cat);
            cmdParams.SetUnsignedIntegerValue(ref WPD_PROPERTY_COMMON_COMMAND_ID, 12);
            cmdParams.SetUnsignedIntegerValue(ref WPD_PROPERTY_MTP_EXT_OPERATION_CODE, (uint)opCode);

            IPortableDevicePropVariantCollection pColl = (IPortableDevicePropVariantCollection)new PortableDevicePropVariantCollectionClass();
            if (parameters != null)
            {
                foreach (uint p in parameters)
                {
                    PROPVARIANT pv = new PROPVARIANT();
                    pv.vt = 19;
                    pv.uintVal = p;
                    pColl.Add(ref pv);
                }
            }
            cmdParams.SetIPortableDevicePropVariantCollectionValue(ref WPD_PROPERTY_MTP_EXT_OPERATION_PARAMS, pColl);

            IPortableDeviceValues results;
            try
            {
                device.SendCommand(0, cmdParams, out results);
            }
            catch (Exception ex)
            {
                Log("    [!] SendCommand failed: " + ex.Message);
                return null;
            }

            uint respCode = 0;
            try
            {
                results.GetUnsignedIntegerValue(ref WPD_PROPERTY_MTP_EXT_RESPONSE_CODE, out respCode);
            }
            catch { }

            if (respCode != 0x2001)
            {
                return null;
            }

            string context = "";
            results.GetStringValue(ref WPD_PROPERTY_MTP_EXT_TRANSFER_CONTEXT, out context);

            MemoryStream ms = new MemoryStream();
            while (true)
            {
                IPortableDeviceValues readCmd = (IPortableDeviceValues)new PortableDeviceValuesClass();
                readCmd.SetGuidValue(ref WPD_PROPERTY_COMMON_COMMAND_CATEGORY, ref cat);
                readCmd.SetUnsignedIntegerValue(ref WPD_PROPERTY_COMMON_COMMAND_ID, 14);
                readCmd.SetStringValue(ref WPD_PROPERTY_MTP_EXT_TRANSFER_CONTEXT, context);
                readCmd.SetUnsignedIntegerValue(ref WPD_PROPERTY_MTP_EXT_BYTES_TO_READ, 65536);

                IPortableDeviceValues readRes;
                try
                {
                    device.SendCommand(0, readCmd, out readRes);
                }
                catch { break; }

                IntPtr pBuf;
                uint cbBuf = 0;
                try
                {
                    readRes.GetBufferValue(ref WPD_PROPERTY_MTP_EXT_DATA, out pBuf, out cbBuf);
                    if (cbBuf > 0 && pBuf != IntPtr.Zero)
                    {
                        byte[] chunk = new byte[cbBuf];
                        Marshal.Copy(pBuf, chunk, 0, (int)cbBuf);
                        Marshal.FreeCoTaskMem(pBuf);
                        ms.Write(chunk, 0, chunk.Length);
                    }
                    else
                    {
                        break;
                    }
                }
                catch
                {
                    break;
                }
            }

            try
            {
                IPortableDeviceValues endCmd = (IPortableDeviceValues)new PortableDeviceValuesClass();
                endCmd.SetGuidValue(ref WPD_PROPERTY_COMMON_COMMAND_CATEGORY, ref cat);
                endCmd.SetUnsignedIntegerValue(ref WPD_PROPERTY_COMMON_COMMAND_ID, 15);
                endCmd.SetStringValue(ref WPD_PROPERTY_MTP_EXT_TRANSFER_CONTEXT, context);
                IPortableDeviceValues endRes;
                device.SendCommand(0, endCmd, out endRes);
            }
            catch { }

            return ms.ToArray();
        }

        static IPortableDevice OpenDevice(string devId)
        {
            IPortableDevice device = (IPortableDevice)new PortableDeviceClass();
            IPortableDeviceValues clientInfo = (IPortableDeviceValues)new PortableDeviceValuesClass();
            clientInfo.SetStringValue(ref WPD_CLIENT_NAME, "OpenEOS");
            clientInfo.SetUnsignedIntegerValue(ref WPD_CLIENT_MAJOR_VERSION, 1);
            clientInfo.SetUnsignedIntegerValue(ref WPD_CLIENT_MINOR_VERSION, 0);

            device.Open(devId, clientInfo);
            return device;
        }

        public static void Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;

            Log("=================================================================");
            Log("   OpenEOS: Опрос PTP-паспорта камеры (GetDeviceInfo 0x1001)");
            Log("=================================================================");
            Log("Режим: БЕЗОПАСНЫЙ (Read-Only опрос дескрипторов PTP)");
            Log();

            try
            {
                Log("[1/3] Поиск интерфейса камеры через Windows Portable Devices...");
                string devId = FindCanonDeviceId();

                if (string.IsNullOrEmpty(devId))
                {
                    Log("[-] Камера Canon не найдена в перечне WPD устройств.");
                    Log("    Проверьте, что камера включена и подключена по USB.");
                    SaveReport();
                    return;
                }

                Log("[+] Найдено устройство: " + devId);
                Log();

                Log("[2/3] Подключение к камере и отправка команды GetDeviceInfo (0x1001)...");
                IPortableDevice device = OpenDevice(devId);

                byte[] raw = ExecuteMtpCommandWithDataToRead(device, 0x1001, null);

                if (raw == null || raw.Length == 0)
                {
                    Log("[-] Камера не ответила на запрос 0x1001 через WPD Pass-Through.");
                    device.Close();
                    SaveReport();
                    return;
                }

                Log("[+] Получен сырой PTP-дескриптор: " + raw.Length + " байт.");
                Log();

                Log("[3/3] Декодирование паспорта PTP (ISO 15740)...");
                PtpDeviceInfo info = PtpDeviceInfo.Parse(raw);

                Log("-----------------------------------------------------------------");
                Log("ПАСПОРТ КАМЕРЫ:");
                Log("  Производитель:      " + info.Manufacturer);
                Log("  Модель:             " + info.Model);
                Log("  Версия прошивки:    " + info.DeviceVersion);
                Log("  Серийный номер:     " + info.SerialNumber);
                Log("  PTP Стандарт:       v" + (info.StandardVersion / 100.0));
                Log("  Vendor Extension:   ID 0x" + info.VendorExtensionId.ToString("X8") + " (v" + (info.VendorExtensionVersion / 100.0) + ")");
                Log("  Описание расшир.:   " + info.VendorExtensionDesc);
                Log("-----------------------------------------------------------------");
                Log();

                Log("ПОДДЕРЖИВАЕМЫЕ ОПЕРАЦИИ (Operations Supported: " + info.OperationsSupported.Count + "):");
                Dictionary<int, string> knownOps = new Dictionary<int, string>()
                {
                    { 0x1001, "GetDeviceInfo" }, { 0x1002, "OpenSession" }, { 0x1003, "CloseSession" },
                    { 0x1004, "GetStorageIDs" }, { 0x1005, "GetStorageInfo" }, { 0x1007, "GetObject" },
                    { 0x1014, "GetDevicePropDesc" }, { 0x1015, "GetDevicePropValue" }, { 0x1016, "SetDevicePropValue" },
                    { 0x9101, "Canon:GetDevicePropDesc" }, { 0x9102, "Canon:GetDevicePropValue" },
                    { 0x9103, "Canon:SetDevicePropValue" }, { 0x9107, "Canon:SetRemoteMode" },
                    { 0x9110, "Canon:CheckEvent" }, { 0x9114, "Canon:GetEvent" },
                    { 0x902C, "Canon:GetStorageIDs" }, { 0x9052, "Canon:Diagnostic/Service" }
                };

                foreach (ushort op in info.OperationsSupported)
                {
                    string hex = "0x" + op.ToString("X4");
                    string name = knownOps.ContainsKey(op) ? " (" + knownOps[op] + ")" : "";
                    Log("    " + hex + name);
                }
                Log();

                Log("ПОДДЕРЖИВАЕМЫЕ СВОЙСТВА (Device Properties Supported: " + info.DevicePropertiesSupported.Count + "):");
                Dictionary<int, string> knownProps = new Dictionary<int, string>()
                {
                    { 0x5001, "BatteryLevel" }, { 0x5003, "ImageSize" }, { 0x5004, "CompressionSetting" },
                    { 0x5005, "WhiteBalance" }, { 0x5007, "FNumber (Aperture)" }, { 0x5008, "FocalLength" },
                    { 0x500B, "FocusMode" }, { 0x500C, "ExposureMeteringMode" }, { 0x500E, "ExposureProgramMode" },
                    { 0x500F, "ExposureIndex (ISO)" }, { 0x5010, "ExposureBiasCompensation" }, { 0x5011, "DateTime" },
                    { 0x5013, "StillCaptureMode" }, { 0xD102, "Canon:ShutterSpeed" }, { 0xD103, "Canon:Aperture" },
                    { 0xD104, "Canon:ISO" }, { 0xD108, "Canon:WhiteBalance" }, { 0xD109, "Canon:ColorTemperature" },
                    { 0xD10B, "Canon:PictureStyle" }, { 0xD10C, "Canon:DriveMode" }, { 0xD10D, "Canon:MeteringMode" },
                    { 0xD114, "Canon:AutoFocusMode" }, { 0xD1A6, "Canon:ShutterCounter (Legacy)" }, { 0xD1B0, "Canon:ShutterCounter2 (Legacy)" },
                    { 0xD047, "Canon:ShutterCount (Experimental)" }
                };

                Log("    Опрос текущих значений свойств (Read-Only):");
                foreach (ushort prop in info.DevicePropertiesSupported)
                {
                    string hex = "0x" + prop.ToString("X4");
                    string pName = knownProps.ContainsKey(prop) ? knownProps[prop] : "Unknown Property";

                    byte[] propValBytes = ExecuteMtpCommandWithDataToRead(device, 0x1015, new uint[] { (uint)prop });
                    string valStr = "";
                    if (propValBytes != null && propValBytes.Length > 0)
                    {
                        if (propValBytes.Length == 1)
                        {
                            valStr = " = " + (int)propValBytes[0] + " (0x" + propValBytes[0].ToString("X2") + ")";
                        }
                        else if (propValBytes.Length == 2)
                        {
                            ushort val = BitConverter.ToUInt16(propValBytes, 0);
                            valStr = " = " + val + " (0x" + val.ToString("X4") + ")";
                        }
                        else if (propValBytes.Length == 4)
                        {
                            uint val = BitConverter.ToUInt32(propValBytes, 0);
                            valStr = " = " + val + " (0x" + val.ToString("X8") + ")";
                        }
                        else
                        {
                            string hexBytes = BitConverter.ToString(propValBytes).Replace("-", " ");
                            if (hexBytes.Length > 30) hexBytes = hexBytes.Substring(0, 30) + "...";
                            valStr = " = [" + propValBytes.Length + " bytes: " + hexBytes + "]";
                        }
                    }
                    else
                    {
                        valStr = " = [unreadable / protected]";
                    }
                    Log("    " + hex + " - " + pName + valStr);
                }

                device.Close();
                Log();
                Log("=================================================================");
                Log("Опрос PTP-паспорта успешно завершён.");
            }
            catch (Exception ex)
            {
                Log("[-] Исключение: " + ex.Message);
            }

            SaveReport();
        }

        static void SaveReport()
        {
            try
            {
                string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "ptp_device_info_report.txt");
                File.WriteAllLines(path, logLines.ToArray(), Encoding.UTF8);
                Log("Полный отчёт сохранён в файл: " + path);
            }
            catch { }
            Log("=================================================================");
        }
    }
}
