using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.Serialization;
using System.ServiceModel;
using System.ServiceModel.Channels;
using System.Text;
using System.Xml;

namespace TisInterop
{
    [DataContract(Namespace = "urn:tis:interop")]
    public enum Color { [EnumMember] Red, [EnumMember] Blue }

    [DataContract(Namespace = "urn:tis:interop")]
    [KnownType(typeof(Derived))]
    public class Base { [DataMember] public string Name; }

    [DataContract(Namespace = "urn:tis:interop")]
    public class Derived : Base { [DataMember] public int Extra; }

    [DataContract(Namespace = "urn:tis:interop")]
    public class All
    {
        [DataMember] public bool B;
        [DataMember] public byte U8;
        [DataMember] public sbyte I8;
        [DataMember] public short I16;
        [DataMember] public ushort U16;
        [DataMember] public int I32;
        [DataMember] public uint U32;
        [DataMember] public long I64;
        [DataMember] public ulong U64;
        [DataMember] public float F;
        [DataMember] public double D;
        [DataMember] public decimal M;
        [DataMember] public char C;
        [DataMember] public string S;
        [DataMember] public string Null;
        [DataMember] public DateTime DtLocal;
        [DataMember] public DateTime DtUtc;
        [DataMember] public DateTime DtUnspec;
        [DataMember] public DateTime DtMidnight;
        [DataMember] public DateTime DtMin;
        [DataMember] public DateTime DtMax;
        [DataMember] public DateTime DtMaxUtc;
        [DataMember] public DateTimeOffset Dto;
        [DataMember] public TimeSpan Ts;
        [DataMember] public TimeSpan TsNeg;
        [DataMember] public Guid G;
        [DataMember] public byte[] Bytes;
        [DataMember] public Uri U;
        [DataMember] public XmlQualifiedName Q;
        [DataMember] public Color E;
        [DataMember] public int[] IntArr;
        [DataMember] public long[] LongArr;
        [DataMember] public short[] ShortArr;
        [DataMember] public double[] DblArr;
        [DataMember] public float[] FltArr;
        [DataMember] public decimal[] DecArr;
        [DataMember] public bool[] BoolArr;
        [DataMember] public DateTime[] DtArr;
        [DataMember] public Guid[] GuidArr;
        [DataMember] public TimeSpan[] TsArr;
        [DataMember] public List<string> Strs;
        [DataMember] public Base Poly;
        [DataMember] public Dictionary<string, int> Map;
        [DataMember] public double[] Specials;
        [DataMember] public float[] FSpecials;
        [DataMember] public decimal[] MSpecials;
        [DataMember] public string Long;
        [DataMember] public string Unicode;
    }

    [DataContract(Namespace = "urn:tis:interop")]
    [KnownType(typeof(Color))]
    [KnownType(typeof(Derived))]
    public class Extra
    {
        [DataMember] public object[] Objs;
        [DataMember] public XmlElement Xml;
    }

    [DataContract(Namespace = "urn:tis:interop")]
    public class Detail
    {
        [DataMember] public int Code;
        [DataMember] public string Text;
    }

    public static class Gen
    {
        public static Extra SampleExtra(int i)
        {
            var doc = new XmlDocument();
            doc.LoadXml("<x:Any xmlns:x='urn:tis:any' a='1'>text <x:Child>" + i + "</x:Child></x:Any>");
            return new Extra
            {
                Objs = new object[] { 1, "s", 2.5, 2.5f, 1.50m, true, (byte)7, (long)-1,
                                      new DateTime(2006, 5, 17, 1, 2, 3, DateTimeKind.Utc),
                                      new Guid("33221100-5544-7766-8899-aabbccddeeff"),
                                      TimeSpan.FromMinutes(90), new byte[] { 1, 2 },
                                      new Uri("http://x/"), Color.Red,
                                      new Derived { Name = "d", Extra = i }, null },
                Xml = doc.DocumentElement
            };
        }

        static Message MakeExtra(string kind, int i)
        {
            Message m;
            if (kind == "fault")
            {
                var fault = MessageFault.CreateFault(
                    FaultCode.CreateSenderFaultCode("InvalidThing", "urn:tis:faults"),
                    new FaultReason("The thing " + i + " is invalid"),
                    new Detail { Code = 42 + i, Text = "détail <&>" },
                    new DataContractSerializer(typeof(Detail)));
                m = Message.CreateMessage(MessageVersion.Soap12WSAddressing10, fault, "urn:tis:interop/Fault");
            }
            else
            {
                m = Message.CreateMessage(MessageVersion.Soap12WSAddressing10, "urn:tis:interop/Extra",
                                          SampleExtra(i), new DataContractSerializer(typeof(Extra)));
            }
            m.Headers.RelatesTo = new UniqueId(new Guid(string.Format("4e1e8f3e-4a3a-4a2b-9e5c-{0:x12}", i)));
            return m;
        }

        public static All Sample(int i)
        {
            var a = new All();
            a.B = true; a.U8 = 255; a.I8 = -128; a.I16 = -32768; a.U16 = 65535;
            a.I32 = -2147483648 + i; a.U32 = 4294967295; a.I64 = long.MinValue;
            a.U64 = ulong.MaxValue; a.F = 32.45f; a.D = 2.718281828459045;
            a.M = 5.123456m; a.C = 'é'; a.S = "a<b>&\"'\r\nc\td " + i; a.Null = null;
            a.DtLocal = new DateTime(2006, 5, 17, 10, 20, 30, 123, DateTimeKind.Local);
            a.DtUtc = new DateTime(2006, 5, 17, 10, 20, 30, DateTimeKind.Utc).AddTicks(1);
            a.DtUnspec = new DateTime(2006, 5, 17, 10, 20, 30, DateTimeKind.Unspecified);
            a.DtMidnight = new DateTime(2006, 5, 17, 0, 0, 0, DateTimeKind.Unspecified);
            a.DtMin = DateTime.MinValue; a.DtMax = DateTime.MaxValue;
            a.DtMaxUtc = DateTime.SpecifyKind(DateTime.MaxValue, DateTimeKind.Utc);
            a.Dto = new DateTimeOffset(2006, 5, 17, 10, 20, 30, TimeSpan.FromHours(-5));
            a.Ts = new TimeSpan(1, 2, 3, 4, 500); a.TsNeg = TimeSpan.FromSeconds(-344);
            a.G = new Guid("33221100-5544-7766-8899-aabbccddeeff");
            a.Bytes = new byte[] { 0, 1, 2, 255 };
            a.U = new Uri("http://example.com/a?b=c&d=e");
            a.Q = new XmlQualifiedName("Local", "urn:tis:qname");
            a.E = Color.Blue;
            a.IntArr = new int[] { 1, 2, -3, int.MaxValue };
            a.LongArr = new long[] { long.MinValue, 0, long.MaxValue };
            a.ShortArr = new short[] { -1, 2 };
            a.DblArr = new double[] { 0.5, 100, 1e-7, 1.5e300 };
            a.FltArr = new float[] { 0.5f, 1.1f, 3.4e38f };
            a.DecArr = new decimal[] { 1.50m, -0.0001m, 79228162514264337593543950335m };
            a.BoolArr = new bool[] { true, false, true };
            a.DtArr = new DateTime[] { a.DtUtc, a.DtUnspec, a.DtLocal };
            a.GuidArr = new Guid[] { a.G, Guid.Empty };
            a.TsArr = new TimeSpan[] { TimeSpan.Zero, TimeSpan.MaxValue, TimeSpan.MinValue };
            a.Strs = new List<string> { "x", "", "y z" };
            a.Poly = new Derived { Name = "derived", Extra = 42 };
            a.Map = new Dictionary<string, int> { { "k1", 1 }, { "k2", 2 } };
            a.Specials = new double[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity, -0.0, double.Epsilon, double.MaxValue, 1e21, 123456789012345680000.0 };
            a.FSpecials = new float[] { float.NaN, float.PositiveInfinity, -0.0f, float.Epsilon, float.MaxValue };
            a.MSpecials = new decimal[] { 0m, -0m, 1.00m, decimal.MinValue, 0.0000000000000000000000000001m };
            a.Long = new string('L', 300);  // Chars16Text; 70000 for Chars32Text
            a.Unicode = "\U0001F600 Grüße";
            return a;
        }

        static string Hex(ArraySegment<byte> s)
        {
            var sb = new StringBuilder(s.Count * 2);
            for (int i = s.Offset; i < s.Offset + s.Count; i++) sb.Append(s.Array[i].ToString("x2"));
            return sb.ToString();
        }

        static byte[] Unhex(string h)
        {
            var b = new byte[h.Length / 2];
            for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(h.Substring(2 * i, 2), 16);
            return b;
        }

        static Message Make(All obj, int i)
        {
            var m = Message.CreateMessage(MessageVersion.Soap12WSAddressing10, "urn:tis:interop/Action", obj,
                                          new DataContractSerializer(typeof(All)));
            m.Headers.To = new Uri("net.tcp://dc.example:9389/Service");
            m.Headers.MessageId = new UniqueId(new Guid(string.Format("4e1e8f3e-4a3a-4a2b-9e5c-{0:x12}", i)));
            return m;
        }

        static string Text(Message m)
        {
            var sb = new StringBuilder();
            var settings = new XmlWriterSettings { OmitXmlDeclaration = true, NewLineHandling = NewLineHandling.Entitize };
            using (var w = XmlWriter.Create(sb, settings)) { m.WriteMessage(w); }
            return sb.ToString();
        }

        // .NET -> python: the WCF binary message encoder, as net.tcp uses it
        public static string Produce(int count)
        {
            var factory = new BinaryMessageEncodingBindingElement().CreateMessageEncoderFactory();
            var bm = BufferManager.CreateBufferManager(0, 1 << 24);
            var outSession = factory.CreateSessionEncoder();
            var inSession = factory.CreateSessionEncoder();
            var plain = factory.Encoder;
            var sb = new StringBuilder();
            for (int i = 0; i < 3 * count; i++)
            {
                string kind = i < count ? "all" : i < 2 * count ? "extra" : "fault";
                foreach (var mode in new[] { "session", "plain" })
                {
                    var enc = mode == "session" ? outSession : plain;
                    var dec = mode == "session" ? inSession : plain;
                    var msg = kind == "all" ? Make(Sample(i), i) : MakeExtra(kind, i);
                    var seg = enc.WriteMessage(msg, 1 << 24, bm);
                    string hex = Hex(seg);
                    var copy = new byte[seg.Count];
                    Array.Copy(seg.Array, seg.Offset, copy, 0, seg.Count);
                    var back = dec.ReadMessage(new ArraySegment<byte>(copy), bm, enc.ContentType);
                    sb.Append(mode).Append('\t').Append(i).Append('\t').Append(hex).Append('\t')
                      .Append(Convert.ToBase64String(Encoding.UTF8.GetBytes(Text(back)))).Append('\n');
                }
            }
            return sb.ToString();
        }

        // python -> .NET: read each message with the WCF encoder, deserialize
        // it, and compare it with Sample(i), member by member
        public static string Consume(string lines)
        {
            var factory = new BinaryMessageEncodingBindingElement().CreateMessageEncoderFactory();
            var bm = BufferManager.CreateBufferManager(0, 1 << 24);
            var session = factory.CreateSessionEncoder();
            var sb = new StringBuilder();
            var ser = new DataContractSerializer(typeof(All));
            foreach (var line in lines.Split(new[] { '\n' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var parts = line.Trim().Split('\t');
                string mode = parts[0]; int i = int.Parse(parts[1]);
                var enc = mode == "session" ? session : factory.Encoder;
                try
                {
                    var msg = enc.ReadMessage(new ArraySegment<byte>(Unhex(parts[2])), bm, enc.ContentType);
                    string action = msg.Headers.Action;
                    var diffs = new List<string>();
                    if (action == "urn:tis:interop/Fault")
                    {
                        var fault = MessageFault.CreateFault(msg, 1 << 20);
                        var detail = fault.GetDetail<Detail>(new DataContractSerializer(typeof(Detail)));
                        string want = "InvalidThing/urn:tis:faults/The thing " + i + " is invalid/" + (42 + i) + "/détail <&>";
                        string got = fault.Code.SubCode.Name + "/" + fault.Code.SubCode.Namespace + "/" +
                                     fault.Reason.GetMatchingTranslation().Text + "/" + detail.Code + "/" + detail.Text;
                        if (!fault.Code.IsSenderFault || want != got) diffs.Add("fault: want " + want + " got " + got);
                    }
                    else if (action == "urn:tis:interop/Extra")
                    {
                        var got = msg.GetBody<Extra>(new DataContractSerializer(typeof(Extra)));
                        var want = SampleExtra(i);
                        string a = Show(want.Objs), b = Show(got.Objs);
                        if (a != b) diffs.Add("Objs: want " + Trunc(a) + " got " + Trunc(b));
                        for (int k = 0; k < want.Objs.Length; k++)
                            if ((want.Objs[k] == null) != (got.Objs[k] == null) ||
                                (want.Objs[k] != null && want.Objs[k].GetType() != got.Objs[k].GetType()))
                                diffs.Add("Objs[" + k + "] type: want " + (want.Objs[k] == null ? "null" : want.Objs[k].GetType().Name) +
                                          " got " + (got.Objs[k] == null ? "null" : got.Objs[k].GetType().Name));
                        // the order of the attributes is not significant (.NET
                        // itself writes the attributes before the declarations)
                        if (Canon(want.Xml) != Canon(got.Xml)) diffs.Add("Xml: want " + want.Xml.OuterXml + " got " + got.Xml.OuterXml);
                    }
                    else
                    {
                        var got = msg.GetBody<All>(ser);
                        var want = Sample(i);
                        if (action != "urn:tis:interop/Action") diffs.Add("Action=" + action);
                        foreach (var f in typeof(All).GetFields())
                        {
                            string a = Show(f.GetValue(want)), b = Show(f.GetValue(got));
                            if (a != b) diffs.Add(f.Name + ": want " + Trunc(a) + " got " + Trunc(b));
                        }
                    }
                    sb.Append(mode).Append('\t').Append(i).Append('\t').Append(diffs.Count == 0 ? "OK" : string.Join(" | ", diffs.ToArray())).Append('\n');
                }
                catch (Exception e)
                {
                    sb.Append(mode).Append('\t').Append(i).Append("\tEXCEPTION ").Append(e.GetType().Name).Append(": ").Append(e.Message.Replace('\n', ' ')).Append('\n');
                }
            }
            return sb.ToString();
        }

        static string Canon(XmlNode node)
        {
            var e = node as XmlElement;
            if (e == null) return node.Value;
            var attrs = new List<string>();
            foreach (XmlAttribute a in e.Attributes) attrs.Add(a.NamespaceURI + "|" + a.LocalName + "=" + a.Value);
            attrs.Sort(StringComparer.Ordinal);
            var sb = new StringBuilder("{" + e.NamespaceURI + "}" + e.LocalName + "[" + string.Join(",", attrs.ToArray()) + "](");
            foreach (XmlNode c in e.ChildNodes) sb.Append(Canon(c)).Append(';');
            return sb.Append(')').ToString();
        }

        static string Trunc(string s) { return s.Length > 80 ? s.Substring(0, 80) + "..." : s; }

        static string Show(object o)
        {
            if (o == null) return "null";
            if (o is DateTime) { var d = (DateTime)o; return d.Ticks + "/" + d.Kind + "/" + d.ToUniversalTime().Ticks; }
            if (o is DateTimeOffset) { var d = (DateTimeOffset)o; return d.UtcTicks + "/" + d.Offset; }
            if (o is double) return ((double)o).ToString("R");
            if (o is float) return ((float)o).ToString("R");
            if (o is decimal) return ((decimal)o).ToString(System.Globalization.CultureInfo.InvariantCulture);
            if (o is Base) { var b = (Base)o; return b.GetType().Name + ":" + b.Name + ((b is Derived) ? ":" + ((Derived)b).Extra : ""); }
            if (o is System.Collections.IDictionary)
            {
                var parts = new List<string>();
                foreach (System.Collections.DictionaryEntry e in (System.Collections.IDictionary)o) parts.Add(e.Key + "=" + e.Value);
                parts.Sort(); return "{" + string.Join(",", parts.ToArray()) + "}";
            }
            if (o is System.Collections.IEnumerable && !(o is string))
            {
                var parts = new List<string>();
                foreach (var x in (System.Collections.IEnumerable)o) parts.Add(Show(x));
                return "[" + string.Join(",", parts.ToArray()) + "]";
            }
            return o.ToString();
        }
    }
}
