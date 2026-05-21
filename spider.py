import requests
from bs4 import BeautifulSoup
import json

#存放所有菜的数据
all_data = []

for page_num in range(0,10):
    url = f"https://www.xiangha.com/caipu/z-recai/hot-{page_num}"
    #url = "https://www.xiangha.com/caipu/z-recai/"
    response = requests.get(url)
    soup_all = BeautifulSoup(response.text,"html.parser")

    recipe_links = []
    for page_link in soup_all.find_all("p",attrs={"class":"name kw"}):
        a_tag = page_link.find("a")
        if a_tag and a_tag.get("href"):
            recipe_links.append(a_tag["href"])

    for link in recipe_links:
        #进入菜谱详情页
        detail_response =requests.get(link)
        soup = BeautifulSoup(detail_response.text,"html.parser")

        dish_title = soup.find("h2", class_="dish-title")
            
        # 没有菜名标签 → 广告/首页 → 跳过
        if not dish_title:
            print("❌ 广告/假链接，跳过：", link)
            continue
        
        #取出菜名
        dish_title = soup.find("h2",class_="dish-title")
        if dish_title:
            name = dish_title.get_text()
        else:
            name = None
            print(f"链接{link}未找到菜名")

        #取出食材
        ingredients = []
        cell_list = soup.find_all("div",class_="cell")
        for cell in cell_list:
            class_list = cell.get("class", [])
            if "cell" in class_list and "kw" not in class_list:
                a_tag = cell.find("a")
                if a_tag:
                    ingredients.append(a_tag.get_text())
        # print(name)
        # print(ingredients)

        dish_info = {
            "recipe_name": name, "ingredients": ingredients
        }
        all_data.append(dish_info)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=4)

# #打印菜名
# for page_num in range(0,10):
#     response = requests.get(f"https://www.xiangha.com/caipu/z-recai/hot-{page_num}")
#     html = response.text
#     soup = BeautifulSoup(html,"html.parser")
#     choose = soup.find_all("p",attrs={"class":"name kw"})
#     for recipe_name in choose:
#         link = recipe_name.find("a")
#         print(link.string)

# #打印食材用料
# for page_num in range(0,10):
#     response = requests.get(f"https://www.xiangha.com/caipu/z-recai/hot-{page_num}")
#     html = response.text
#     soup = BeautifulSoup(html,"html.parser")
#     choose = soup.find_all("p",attrs={"class":"name kw"})
#     for recipe_name in choose:
#         link = recipe_name.find("a")
#         print(link.string)