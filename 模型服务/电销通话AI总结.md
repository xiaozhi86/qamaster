# 接口定义

## 单通通话AI分析接口

* 前置处理：消费MQ消息数据，判断ElectrinRecordInfo.recodeDuration是否大于等于预设值，满足则请求接口做单通AI总结，否则丢弃该数据，其中预设值是apollo自定义配置，配置后立即生效。

* 请求接口重试：可设置重试次数，重试次数达到上限次数后仍然失败，则丢弃该数据，不异步回调电销系统

* 入参：

```json
{
  "user_no": "xxxxxx",
  "connection_time": "xxxxx", # 接通时间
  "duration_seconds": 20.1, # 通话时长,毫秒
  "conversation": [ # 对话内容
    {"role": "assistant", "content": "xxxxx", "start_time": 1},   
    {"role": "user", "content": "xxxxxxxx", "start_time": 2}
  ]
}
```
* 输入字段取值说明：

   * user_no:取自MQ消息中electrinRecordInfo.custNo

   * connection_time:取自MQ消息中electrinRecordInfo.recordStartTime

   * duration_seconds:取自MQ消息中electrinRecordInfo.recodeDuration

   * conversation.role:MQ消息中textInfo.channel为0时，该值为assistant，为1时，该值为user

   * conversation.content：取自MQ消息中textInfo.text

   * conversation.start_time:取自MQ消息中textInfo.startTime

   * conversation下的数据需要和MQ消息中的textInfo下的数据的顺序一致

* 出参：

```json
{
  "user_no": "xxxxxx", 
  "connection_time": "xxxxx",
  "duration_seconds": 20.1,
  "callSheetId":"xxxxx", 
  "summary": "xxxxxxxxxxxxx", # AI智能总结、AI摘要合并到一个字段
  "labels": [ 
    {
      "value": "期望灵活还款",    
      "category": "客户期望类",  
      "evidence": "xxxxx"  # 原文
    },
    {"value": "担心隐形费用", "category": "客户异议类", "evidence": "xxxxxxxx"}
  ],
  "cust_intent_score": 5, # 客户意向分
  "cust_objection_score": 1, # 客户异议分
  "cust_failure_score": 0,  # 客户失败分
  "evaluation": {    # AI评分/质检
    "score": 85.5  # AI评分    
    "evaluation_dimensions": [
      {
        "name": "xxx", # 评分维度
        "score": 90
      },
      {"name": "zzz": "score": 81},
     ...
    ]
  },
  "hungup_node": "xxxx",   # 模型计算出的挂机节点
  "electrinRecordInfo":{}  #透传mq消息中的electrinRecordInfo
}
```
* 输出字段说明：
  * callSheetId：取自mq消息中的electrinRecordInfo.callSheetId
  * labels.category:通话标签枚举中的一级标签
  * labels.value:通话标签枚举中的子标签
  * user_no:取自MQ消息中electrinRecordInfo.custNo
  * connection_time:取自MQ消息中electrinRecordInfo.recordStartTime
  * duration_seconds:取自MQ消息中electrinRecordInfo.recodeDuration
* 接口成功数据异步请求电销dubbo接口，请求接口异常时需要利用kafka topic的重试机制重试，到重试上限次数仍然失败，则丢弃，teams告警。

## 

## 客户特征ai分析建议接口

* 入参（输入是业务聚合的三类特征）

```json
 {
   # 意向客户特征
    "raw_prospective_cust_feature": {
        "一级标签1": {
            "totals": 20,
            "二级标签1": 10,
            "二级标签2": 20,
            "二级标签3": 1
        },
        "一级标签2": {
            "totals": 10,
            "二级标签11": 3,
            "二级标签22": 5,
            "二级标签33": 4
        }
    },
    # 异议客户特征
    "raw_objecting_cust_feature": {
        "一级标签1": {
            "totals": 20,
            "二级标签1": 10,
            "二级标签2": 20,
            "二级标签3": 1
        },
        "一级标签2": {
            "totals": 10,
            "二级标签11": 3,
            "二级标签22": 5,
            "二级标签33": 4
        }
    },
    # 失败客户特征
    "raw_failed_cust_feature": {
        "一级标签1": {
            "totals": 20,
            "二级标签1": 10,
            "二级标签2": 20,
            "二级标签3": 1
        },
        "一级标签2": {
            "totals": 10,
            "二级标签11": 3,
            "二级标签22": 5,
            "二级标签33": 4
        }
    }
}  
```
* 出参

```json
{  
  'prospective_cust_feature': [],
  'objecting_cust_feature': [],
  'failed_cust_feature': [],
  'assitant_performance': 'xxxxxx',
  'conversion_breakpoint': 'xxxxxxxxx',
  'summary': 'xxxxxxx'
}
```
## 挂机节点ai分析建议接口

* 入参: 

```json
{
    "开场白挂断": {
        "totals": 20,
        "客户主要关注点1": 10,
        "客户主要关注点2": 20,
        "客户主要关注点3": 1
    },
    "异议处理挂断": {
        "totals": 10,
        "客户主要关注点11": 3,
        "客户主要关注点22": 5,
        "客户主要关注点33": 4
    }
...
}
```
* 出参：

```json
{  
  'ai_advice': 'xxxxxxxxxxxx'
}
```


# 通话标签枚举s

|一级标签|子标签|含义|典型示例话术|
|:----|:----|:----|:----|
|客户失败类|信号/网络问题|因信号差、网络不稳定导致无法完成操作|"我这边信号不好。""网络卡住了。""在电梯里没网。""山里信号不行。""地下车库没信号。"|
|定义：客户在申请授信/申请用信过程中操作失败，或因客观原因无法按照要求完成相关操作。|未安装相关APP|客户手机上未安装360/银行卡APP等必要应用|"我没下载你们APP。""还要下什么APP？太麻烦了。""手机内存不够装不了。""我不用应用商店。"|
||不会操作/操作困难|客户不熟悉手机操作流程，不知道如何完成|"这个怎么弄？""我不会操作。""你教我一下这个步骤。""年纪大了搞不懂这些东西。""字太小看不清。"|
||忘记密码/登录失败|忘记登录密码、交易密码或身份验证失败|"密码忘了。""登录不上去。""验证码收不到。""人脸识别过不去。""短信验证码一直不来。"|
||人脸识别失败|客户进行人脸识别时多次失败|"人脸一直过不去。""识别了好几次都不行。""光线不好识别不了。""说我与身份证不像。"|
||短信验证码问题|收不到短信验证码或验证码过期|"验证码一直收不到。""短信延迟太久了。""验证码输进去说错误。""号码换了收不到短信。"|
||银行卡问题|银行卡不支持、未绑定、限额、余额不足等|"我这卡不支持。""银行卡绑不上。""提示我卡号不对。""这卡没开通网银。""卡里没钱。"|
||身份证/资料问题|身份证过期、照片不清晰、资料填写错误等|"身份证过期了。""拍了好几次都不通过。""信息填错了改不了。""上传不了照片。"|
||设备/系统不兼容|手机型号、系统版本不兼容导致无法操作|"我的手机太老了不支持。""苹果系统不行。""一直闪退。""安卓版本太低了。"|
||额度/用信被拒|客户操作后系统审核不通过、额度为0或借款失败|"审核没过。""额度是0。""借不出来。""提示综合评分不足。""显示暂不符合条件。"|
||操作超时/中断|操作过程中超时或被打断导致失败|"弄到一半超时了。""刚有人找我，回来就退出去了。""验证码过期了。""页面自动退出了。"|
||主动放弃操作|客户在操作过程中因嫌麻烦等原因主动放弃|"太麻烦了不弄了。""步骤太多了算了。""弄半天弄不好，不搞了。""手头有事，回头再说。"|
||第三方服务异常|银行、运营商等第三方服务异常导致失败|"银行那边提示系统维护。""运营商接口超时。""支付通道异常。"|
||其他操作失败|其他未归类的客观原因导致操作失败|"不知道为什么就是不行。""试了好几次都失败。""所有步骤都做了还是不行。"|



