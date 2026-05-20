"""
创建黔江区2026年度综合考核实施方案
用法: python create_2026_plan.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app, db
from models import (
    Plan, EvaluationDimension, AssessmentDimension, AssessedGroup,
    GroupDimensionWeight, Organization, Unit
)
from datetime import date

if __name__ == "__main__":
    with app.app_context():
        # ============================================================
        # 1. 考核方案
        # ============================================================
        plan_name = "黔江区2026年度综合考核实施方案"
        existing = Plan.query.filter_by(name=plan_name).first()
        if existing:
            print(f"方案已存在: {existing.name} (id={existing.id}), 删除重建")
            db.session.delete(existing)
            db.session.commit()

        plan = Plan(
            name=plan_name,
            year=2026,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            created_date=date.today(),
            status="draft",
        )
        db.session.add(plan)
        db.session.flush()
        print(f"方案已创建: id={plan.id}")

        # 单位实际考核
        eval_dim = EvaluationDimension(name="单位实际考核", score=100, is_actual_assessment=True, plan_id=plan.id)
        db.session.add(eval_dim)
        db.session.flush()

        # ============================================================
        # 2. 考核维度 (13个)
        # ============================================================
        DIMENSIONS = [
            "党的建设", "经济发展", "平安稳定", "生态环保", "服务民生",
            "885考核", "市级部门考核", "项目建设", "改革亮点",
            "招商引资", "业务工作", "其他工作", "专班评价",
        ]
        dim_map = {}
        for dname in DIMENSIONS:
            ad = AssessmentDimension(name=dname, evaluation_dimension_id=eval_dim.id)
            db.session.add(ad)
            db.session.flush()
            dim_map[dname] = ad
        print(f"考核维度: {len(dim_map)}个")

        # ============================================================
        # 3. 组织机构（7大板块）
        # ============================================================
        CATEGORIES = [
            "乡镇街道", "区级部门", "区管国企", "区管学校",
            "区管医院及部分卫生事业单位", "重点工作专班", "部分中央市在黔单位",
        ]
        qj_org = Organization.query.filter_by(name="黔江区").first()
        org_map = {}
        for cat in CATEGORIES:
            org = Organization.query.filter_by(name=cat, parent_id=qj_org.id).first()
            if not org:
                org = Organization(name=cat, parent_id=qj_org.id)
                db.session.add(org)
                db.session.flush()
            org_map[cat] = org
        print(f"组织机构: {len(org_map)}个板块")

        # ============================================================
        # 4. 14个被考核分组 (含单位列表+维度权重)
        # ============================================================
        ALL_GROUPS = {
            # ============ 乡镇街道 4组 ============
            "乡镇街道一组": {
                "org": "乡镇街道",
                "units": ["城东街道", "城南街道", "城西街道", "正阳街道", "舟白街道"],
                "weights": {"党的建设": 25, "经济发展": 25, "平安稳定": 30, "生态环保": 5, "服务民生": 15},
            },
            "乡镇街道二组": {
                "org": "乡镇街道",
                "units": ["冯家街道", "黄溪镇", "石会镇", "濯水镇", "太极镇", "马喇镇", "阿蓬江镇"],
                "weights": {"党的建设": 25, "经济发展": 25, "平安稳定": 25, "生态环保": 5, "服务民生": 20},
            },
            "乡镇街道三组": {
                "org": "乡镇街道",
                "units": ["水市镇", "鹅池镇", "石家镇", "金溪镇", "五里镇", "邻鄂镇", "中塘镇",
                          "小南海镇", "黎水镇", "白石镇", "黑溪镇", "沙坝镇"],
                "weights": {"党的建设": 25, "经济发展": 20, "平安稳定": 25, "生态环保": 5, "服务民生": 25},
            },
            "乡镇街道四组": {
                "org": "乡镇街道",
                "units": ["新华乡", "白土乡", "蓬东乡", "杉岭乡", "水田乡", "金洞乡"],
                "weights": {"党的建设": 25, "经济发展": 20, "平安稳定": 20, "生态环保": 5, "服务民生": 30},
            },
            # ============ 区级部门 4组 ============
            "区级部门一组（综合统筹类）": {
                "org": "区级部门",
                "units": [
                    "区人大常委会机关", "区政协机关", "区委办公室（区委改革办）",
                    "区政府办公室", "区纪委监委机关（区委巡察办）",
                    "区委组织部（区委直属机关工委）", "区委宣传部", "区委统战部", "区委政法委",
                ],
                "weights": {"党的建设": 20, "885考核": 15, "市级部门考核": 15, "项目建设": 5,
                           "改革亮点": 5, "招商引资": 10, "业务工作": 5, "其他工作": 20, "专班评价": 5},
            },
            "区级部门二组（经济发展类）": {
                "org": "区级部门",
                "units": [
                    "区发展改革委", "区科技局", "区财政局", "区规划自然资源局",
                    "区住房城乡建委", "区生态环境局", "区城市管理局", "区林业局",
                    "区水利局", "区农业农村委（区农技中心、区畜牧中心）", "区商务委",
                    "区国资委", "区供销合作社", "区交通运输委（区公路中心）",
                    "区文化旅游委", "黔江高新区管委会（区经济信息委、区招商投资局）",
                    "区工商联", "区教委（区教育考试中心）", "区人力社保局（区社保中心）",
                    "区卫生健康委", "区市场监管局", "区大数据发展局",
                ],
                "weights": {"党的建设": 15, "885考核": 20, "市级部门考核": 10, "项目建设": 20,
                           "改革亮点": 5, "招商引资": 10, "业务工作": 10, "其他工作": 5, "专班评价": 5},
            },
            "区级部门三组（公共管理类）": {
                "org": "区级部门",
                "units": [
                    "区委社会工作部", "区委编办", "区委网信办", "区民政局",
                    "区应急局", "区公安局", "区民族宗教委", "区医保局",
                    "区退役军人事务局", "区司法局", "区信访办", "区统计局",
                ],
                "weights": {"党的建设": 15, "885考核": 15, "市级部门考核": 15, "项目建设": 5,
                           "改革亮点": 10, "招商引资": 10, "业务工作": 10, "其他工作": 18, "专班评价": 2},
            },
            "区级部门四组（社会服务类）": {
                "org": "区级部门",
                "units": [
                    "区融媒体中心", "区行政服务中心", "区机关事务中心", "区委老干局",
                    "区委党校", "区文联", "区总工会", "团区委", "区妇联", "区残联",
                    "区科协", "区史志研究室", "区档案馆",
                ],
                "weights": {"党的建设": 15, "项目建设": 5, "改革亮点": 10, "招商引资": 5,
                           "业务工作": 25, "其他工作": 35, "专班评价": 5},
            },
            # ============ 区管国企 1组 ============
            "区管国企": {
                "org": "区管国企",
                "units": ["国汇（鸿业）集团", "区城运集团", "峡谷城文旅集团", "中新绿雅农业公司"],
                "weights": {"党的建设": 15, "项目建设": 20, "改革亮点": 10, "招商引资": 15,
                           "业务工作": 30, "其他工作": 5, "专班评价": 5},
            },
            # ============ 区管学校 1组 ============
            "区管学校": {
                "org": "区管学校",
                "units": ["区职教中心", "黔江电大", "黔江中学", "新华中学", "民族中学"],
                "weights": {"党的建设": 20, "项目建设": 10, "改革亮点": 20,
                           "业务工作": 40, "其他工作": 5, "专班评价": 5},
            },
            # ============ 区管医院 1组 ============
            "区管医院及部分卫生事业单位": {
                "org": "区管医院及部分卫生事业单位",
                "units": ["中心医院", "区中医院", "区疾控中心", "区妇幼保健院", "黔江中心血站", "区健康管理中心"],
                "weights": {"党的建设": 20, "项目建设": 5, "改革亮点": 20, "招商引资": 5,
                           "业务工作": 40, "其他工作": 5, "专班评价": 5},
            },
            # ============ 重点工作专班 1组 ============
            "重点工作专班": {
                "org": "重点工作专班",
                "units": [
                    "城市专班（区委办公室）", "党建专班（区委组织部）",
                    "营商环境专班（区发展改革委）", "工业专班（黔江高新区管委会）",
                    "农业四个工厂化专班（区农业农村委）", "文旅专班（区文化旅游委）",
                    "增收专班（区人力社保局）", "区域医疗中心专班（区卫生健康委）",
                ],
                "weights": {"项目建设": 20, "改革亮点": 10, "业务工作": 50, "其他工作": 20},
            },
            # ============ 中央市在黔单位 2组 ============
            "部分中央市在黔单位一组（党组织关系在黔）": {
                "org": "部分中央市在黔单位",
                "units": [
                    "区法院", "区检察院", "区审计局", "黔江区税务局", "区气象局",
                    "国家统计局黔江调查队", "中邮黔江分公司", "区烟草专卖局",
                    "中国电信黔江分公司", "黔江卷烟厂",
                ],
                "weights": {"党的建设": 10, "业务工作": 70, "其他工作": 20},
            },
            "部分中央市在黔单位二组（党组织关系不在黔）": {
                "org": "部分中央市在黔单位",
                "units": [
                    "区人武部", "区消防救援局", "中石油黔江销售分公司",
                    "中国移动重庆公司黔江分公司", "中国联通重庆市黔江区分公司",
                    "国网重庆黔江供电公司", "人行黔江分行",
                    "国家金融监管总局黔江监管分局", "黔江海关",
                ],
                "weights": {"业务工作": 80, "其他工作": 20},
            },
        }

        assert len(ALL_GROUPS) == 14, f"分组数应为14，实际为{len(ALL_GROUPS)}"

        # 创建单位并关联机构
        unit_by_name = {}
        created_units = 0
        for gname, gdata in ALL_GROUPS.items():
            org = org_map[gdata["org"]]
            for uname in gdata["units"]:
                unit = Unit.query.filter_by(name=uname).first()
                if not unit:
                    unit = Unit(name=uname, org_id=org.id)
                    db.session.add(unit)
                    db.session.flush()
                    created_units += 1
                else:
                    if unit.org_id != org.id:
                        unit.org_id = org.id
                unit_by_name[uname] = unit
        print(f"单位: 新增{created_units}个, 总计{len(unit_by_name)}个")

        # 创建被考核分组 + 权重
        groups_created = 0
        for gname, gdata in ALL_GROUPS.items():
            total_w = sum(gdata["weights"].values())
            if abs(total_w - 100) > 0.1:
                factor = 100.0 / total_w
                gdata["weights"] = {k: round(v * factor, 1) for k, v in gdata["weights"].items()}
                diff = 100 - sum(gdata["weights"].values())
                if diff != 0:
                    last_key = list(gdata["weights"].keys())[-1]
                    gdata["weights"][last_key] = round(gdata["weights"][last_key] + diff, 1)

            group = AssessedGroup(name=gname, plan_id=plan.id)
            db.session.add(group)
            db.session.flush()

            unit_ids = [unit_by_name[u].id for u in gdata["units"] if u in unit_by_name]
            if unit_ids:
                group.units = Unit.query.filter(Unit.id.in_(unit_ids)).all()

            for dname, weight in gdata["weights"].items():
                if dname in dim_map and weight > 0:
                    db.session.add(GroupDimensionWeight(
                        group_id=group.id,
                        assessment_dimension_id=dim_map[dname].id,
                        weight=float(weight),
                    ))
            groups_created += 1
        print(f"被考核分组: {groups_created}个")

        # ============================================================
        # 5. 主考单位
        # ============================================================
        ASSESSOR_NAMES = [
            "区纪委监委机关（区委巡察办）", "区委组织部（区委直属机关工委）",
            "区委宣传部", "区委统战部",
            "区委办公室（区委改革办）", "区委区政府督查工作专班",
            "区重点办", "区招商办",
        ]
        assessor_ids = []
        for aname in ASSESSOR_NAMES:
            unit = Unit.query.filter_by(name=aname).first()
            if not unit:
                unit = Unit(name=aname, org_id=qj_org.id)
                db.session.add(unit)
                db.session.flush()
            assessor_ids.append(unit.id)
        plan.assessor_units = Unit.query.filter(Unit.id.in_(assessor_ids)).all()
        print(f"主考单位: {len(assessor_ids)}个")

        db.session.commit()

        print("\n====== 2026年度考核方案创建完成 ======")
        print(f"方案: {plan.name}")
        print(f"考核维度: 13个")
        print(f"被考核分组: {groups_created}个")
        print(f"主考单位: {len(assessor_ids)}个")
        print(f"方案ID: {plan.id}")
