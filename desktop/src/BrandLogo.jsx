import wechat from "./assets/wechat.svg";
import feishu from "./assets/feishu.ico";

export default function BrandLogo({ brand }) {
  return (
    <img
      className={`brand-logo ${brand}`}
      src={brand === "wechat" ? wechat : feishu}
      alt={brand === "wechat" ? "微信" : "飞书"}
      draggable="false"
    />
  );
}
